"""Reduced moist-column / horizontal-flow model, NOT a full NWP solver.

Terrain-following layered heat and water advection; parameterized convective
mass flux; condensation, warm-rain conversion, sedimentation and evaporation;
prognostic low-level wind, independent synoptic cold-air tracer and rain-cooled
anomaly. Pressure is hydrostatic/reference, vertical motion is diagnosed.
No prescribed storm objects, tracks, birthdays, speeds or rain masks.
"""
import json
import math
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter, zoom
from .terrain import grid
from .thermo import RD, CP, G, LV, saturation, saturation_ice, dewpoint, parcel, virtual
from .numerics import Advection
from .coldpool import advance as advance_cold_pool, velocity as cold_velocity
from .precipitation import SurfaceRain
from .synoptic import SynopticDriver

VERSION = '4.15.0-rear-circulation'
LF = 333700.  # freezing/melting latent heat, J/kg
Z = np.array([30,150,350,650,1000,1500,2200,3200,4500,6000,8000,10500,13500,16500.],dtype=float)
DZ = np.diff(np.r_[0,(Z[:-1]+Z[1:])/2,18000])


def source_digest(*extra):
    import hashlib
    return hashlib.sha256(b''.join(Path(__file__).with_name(name).read_bytes()
        for name in ['core.py','numerics.py','thermo.py','coldpool.py','precipitation.py','synoptic.py','terrain.py','run.py',*extra])).hexdigest()


def settings(raw, *, grid_limit=12):
    base=json.loads((Path(__file__).with_name('config.json')).read_text())
    unknown=set(raw)-set(base)
    if unknown: raise ValueError('Unknown settings: '+','.join(sorted(unknown)))
    base.update(raw)
    limits={'seed':(1,2147483646),'hours':(.1,96),'grid_km':(4,grid_limit),'frame_minutes':(10,240),
            'month':(3,5),'moisture':(.7,1.3),'jet':(.5,1.5),'shear':(.5,1.5),
            'trough':(0,1.5),'cold_reservoir':(.5,1.5),'sst_c':(18,29),'stochastic':(0,1.5)}
    for key,(lo,hi) in limits.items():
        v=base[key]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:
            raise ValueError(f'{key} must be in [{lo},{hi}]')
    if int(base['seed'])!=base['seed'] or int(base['month'])!=base['month']: raise ValueError('seed/month must be integers')
    b=base['bounds']
    if not isinstance(b,list) or len(b)!=4 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in b): raise ValueError('Invalid bounds')
    if not (100<=b[0]<b[2]<=122 and 18<=b[1]<b[3]<=30) or (b[2]-b[0])*(b[3]-b[1])>100: raise ValueError('Domain too large or outside South China')
    if not isinstance(base['terrain'],bool): raise ValueError('terrain must be boolean')
    if not isinstance(base['compact_transport'],bool):raise ValueError('compact_transport must be boolean')
    return base


def correlated(rng, shape, cells=9):
    coarse=rng.standard_normal((max(3,math.ceil(shape[0]/cells)),max(3,math.ceil(shape[1]/cells))))
    a=zoom(coarse,(shape[0]/coarse.shape[0],shape[1]/coarse.shape[1]),order=1)
    a=gaussian_filter(a, max(1,cells/4),mode='reflect')[:shape[0],:shape[1]]
    return ((a-a.mean())/max(float(a.std()),1e-9)).astype('float32')


def transport(a,u,v,dt,dx,boundary=None):
    """Conservative donor-cell flux with open boundaries.

    Returns the transported extensive field; no wrapping across boundaries.
    Outflow is zero-gradient; optional upstream environment supplies inflow.
    Inputs broadcast over any leading level dimension. CFL checked by caller.
    """
    outside=a if boundary is None else np.broadcast_to(boundary,a.shape)
    ax=np.concatenate((outside[...,:1],a,outside[...,-1:]),axis=-1)
    ay=np.concatenate((outside[...,:1,:],a,outside[...,-1:,:]),axis=-2)
    ux=np.concatenate((u[...,:1],(u[...,:-1]+u[...,1:])*.5,u[...,-1:]),axis=-1)
    vy=np.concatenate((v[...,:1,:],(v[...,:-1,:]+v[...,1:,:])*.5,v[...,-1:,:]),axis=-2)
    fx=ux*np.where(ux>=0,ax[...,:-1],ax[...,1:])
    fy=vy*np.where(vy>=0,ay[...,:-1,:],ay[...,1:,:])
    return a-dt/dx*(np.diff(fx,axis=-1)+np.diff(fy,axis=-2))


def advect(a,u,v,dt,dx,boundary=None,conservative=False):
    """Limited MUSCL / SSP-RK2 scalar advection; summed CFL <= .45.

    First-order donor-cell advection diffused cold-pool edges before they
    could regenerate convection. Minmod reconstruction retains boundaries
    without sharpening a field by hand or inventing an outflow track.
    The face divergence correction preserves a constant scalar exactly.
    """
    return Advection(u,v,dx)(a,dt,boundary,conservative)


def limited_transport(a,u,v,dt,dx,boundary=None):
    """Conservative MUSCL/SSP-RK2 flux for water and density-current volume."""
    return advect(a,u,v,dt,dx,boundary,conservative=True)


def daylight(time):
    hour=(8+time/3600)%24
    return max(0,math.sin((hour-6)*math.pi/12))


def mix_boundary_layer(temp,q,p,mass,u,v,dt,sun,land):
    """Conservative adjacent-layer turbulent exchange below the PBL top.

    Surface fluxes enter the bottom layer; Richardson-limited mixing lets
    them reach the plume's source reservoir rather than moistening just a
    90 m cell. Each pair returns the same dry-air mass and exchanges theta
    and vapour, so no additional water source is introduced.
    """
    theta=temp*(100000/p)**(RD/CP)
    top=np.where(land,350+1000*sun,650)
    density=mass/DZ[:,None,None]
    for k in range(len(Z)-1):
        dz=Z[k+1]-Z[k];height=(Z[k+1]+Z[k])*.5
        shear=((u[k+1]-u[k])**2+(v[k+1]-v[k])**2)/dz**2
        stability=G*(theta[k+1]-theta[k])/(np.maximum(theta[k],200)*dz)
        ri=stability/np.maximum(shear,1e-5)
        coefficient=(12+100*sun*land)*np.maximum(1-height/top,0)**2
        coefficient*=np.clip(1/(1+5*np.maximum(ri,0)),0,1)*(1+np.minimum(np.maximum(-ri,0),2))
        exchanged=np.minimum(coefficient*(density[k]+density[k+1])*.5*dt/dz,
                             .3*np.minimum(mass[k],mass[k+1]))
        water=exchanged*(q[k]-q[k+1])
        heat=exchanged*(theta[k]-theta[k+1])
        q[k]-=water/mass[k];q[k+1]+=water/mass[k+1]
        theta[k]-=heat/mass[k];theta[k+1]+=heat/mass[k+1]
    return (theta*(p/100000)**(RD/CP)).astype('float32'),q


def free_convection_height(result,temp,q,p):
    """Interpolate the first buoyant crossing ABOVE the parcel's own LCL.

    Includes the parcel's source height: an elevated parcel need not be
    lifted all the way from the ground. No buoyant crossing returns infinity.
    """
    pq=np.minimum(result['source_mixing_ratio'][None],saturation(result['path'],p))
    delta=virtual(result['path'],pq)-virtual(temp,q)
    lfc=np.full(temp.shape[1:],np.inf)
    plcl=result['lcl_pressure'];start=result['start_index']
    for k in range(1,len(Z)):
        layer=Z[k]-Z[k-1]
        fraction=np.clip(-delta[k-1]/np.maximum(delta[k]-delta[k-1],1e-9),0,1)
        lcl_fraction=np.clip(np.log(plcl/p[k-1])/np.log(p[k]/p[k-1]),0,1)
        crossing=Z[k-1]+layer*np.maximum(fraction,lcl_fraction)
        eligible=(k>start)&(p[k]<plcl)&(delta[k]>0)
        lfc=np.where(eligible,np.minimum(lfc,crossing),lfc)
    return lfc


def sediment(rain, mass, dt, speed=6.):
    """Conservative vertical flux with its OWN CFL, including thin low layers.

    A positivity-only exponential step let rain fall at most ONE layer each
    90 s step, making a 90 m bottom layer an artificial rain bottleneck.
    """
    speed=np.broadcast_to(np.asarray(speed,dtype=rain.dtype),rain.shape)
    fraction_per_second=speed/DZ[:,None,None]
    count=max(1,math.ceil(float(fraction_per_second.max())*dt/.8))
    fraction=fraction_per_second*(dt/count)
    water=rain*mass;surface=np.zeros(rain.shape[1:],dtype=water.dtype)
    for _ in range(count):
        falling=water*fraction;water-=falling
        water[:-1]+=falling[1:];surface+=falling[0]
    return water/mass,surface


def rain_fall_speed(rain,density,fraction=1.,moment=4):
    """Atlas drop velocity integrated over a Marshall-Palmer size spectrum.

    N(D)=8e6 exp(-lambda D), SI units; water content determines lambda.
    moment=4 gives mass-weighted speed; moment=7 is reflectivity-weighted.
    Density correction approximates faster fall aloft. This remains a
    single-moment closure, not a prognostic drop-number distribution.
    """
    concentration=np.maximum(rain*density/np.maximum(fraction,.01),1e-12)
    slope=(math.pi*1000*8e6/concentration)**.25
    velocity=np.maximum(.1,9.65-10.3*(slope/(slope+600))**moment)
    return velocity*(1.225/np.maximum(density,.1))**.4


def collection_rate(rain,density,fraction=1.):
    """Cloud-drop sweepout by the SAME MP rain spectrum and Atlas velocity.

    Integrate E*pi/4 * N(D)*D**2*V(D) dD (s^-1), collection efficiency .8.
    This transfers existing liquid cloud water, never creates rainwater.
    """
    concentration=np.maximum(rain*density/np.maximum(fraction,.01),1e-15)
    slope=(math.pi*1000*8e6/concentration)**.25
    sweep=.8*math.pi/2*8e6*np.maximum(9.65/slope**3-10.3/(slope+600)**3,0)
    return np.where(rain>0,sweep*(1.225/np.maximum(density,.1))**.4,0)


def rain_evaporation_rate(rain,density,temperature,pressure,fraction=1.):
    """Fractional drop evaporation per unit relative saturation deficit.

    Diffusional mass loss integrated over the SAME Marshall--Palmer spectrum
    used for sedimentation/collection, with heat-conduction resistance and
    ventilation evaluated at the evaporation-weighted diameter 2/lambda.
    Heavy rain contains larger drops: a fixed 180-s fractional loss erased
    too much of it while generating excessively fast, bowed cold currents.
    This is a single-moment approximation, not prognostic drop-number physics.
    """
    concentration=np.maximum(rain*density/np.maximum(fraction,.01),1e-12)
    slope=(math.pi*1000*8e6/concentration)**.25
    diffusion=2.21e-5*(temperature/273.15)**1.94*(101325/pressure)
    conductivity=.024*(temperature/273.15)**.9
    vapor_density=density*saturation(temperature,pressure)
    resistance=1+LV*diffusion*vapor_density/(conductivity*temperature)*(LV/(461.5*temperature)-1)
    diameter=2/slope
    speed=np.maximum(.1,9.65-10.3*np.exp(-600*diameter))*(1.225/np.maximum(density,.1))**.4
    viscosity=1.5e-5*(temperature/273.15)**1.75*(1.225/np.maximum(density,.1))
    ventilation=np.maximum(1,.78+.308*(viscosity/diffusion)**(1/3)*np.sqrt(speed*diameter/viscosity))
    rate=2*diffusion*vapor_density*slope**2/1000*ventilation/np.maximum(resistance,1)
    return np.where(rain>0,rate,0)


def graupel_echo(water,area,density):
    fraction=np.clip(area/np.maximum(water,1e-15),.01,1)
    return 2000*fraction*(np.maximum(water,0)*density*1000/fraction)**1.75


def echo_components(rain,plume_rain,rain_area,density,anvil=None,graupel=None,graupel_area=None):
    conv=np.minimum(np.maximum(plume_rain,0),rain)*density*1000
    environment=np.maximum(rain-plume_rain,0)*density*1000
    fraction=np.clip(rain_area/np.maximum(plume_rain,1e-15),.01,1)
    background=20000*(1-fraction)*environment**1.75
    cores=20000*fraction*(environment+conv/fraction)**1.75
    frozen=np.zeros_like(background) if anvil is None else 2000*np.maximum(anvil*density*1000,0)**1.75
    if graupel is not None:frozen+=graupel_echo(graupel,graupel_area,density)
    return background,cores,frozen,fraction


def rain_reflectivity(rain, plume_rain, rain_area, density, anvil=None,graupel=None,graupel_area=None):
    """Volume-mean linear Z of environmental rain and finite-area plumes.

    Rain and plume rain are grid-mean mixing ratios; the latter is a SUBSET.
    rain_area transports plume_rain * occupied area, so a drifting shower
    does not acquire the fraction of an unrelated new updraft beneath it.
    Average linear backscatter, never dBZ or a diluted water concentration.
    This remains a warm-rain, Marshall-Palmer approximation, not hail radar.
    """
    background,cores,frozen,_=echo_components(rain,plume_rain,rain_area,density,anvil,graupel,graupel_area)
    # Frozen condensate scatters less efficiently than liquid rain. Its
    # water is prognostic, NOT a halo painted on the cold-pool mask.
    linear=background+cores+frozen
    return 10*np.log10(np.maximum(linear,1e-3))


class Model:
    # Smooth moist middle troposphere for the spring warm-sector scenarios.
    # The seeded moisture parameter, real parcel/debt budgets and northern
    # cold-air drying still apply; this is an INITIAL water reservoir only.
    MIDLEVEL_HUMIDITY_BOOST=.17
    WARM_PATTERN_RETENTION=.70

    def __init__(self, config, height, *, grid_limit=12, astra_updates=True):
        self.cfg=settings(config,grid_limit=grid_limit);c=self.cfg
        self.astra_updates=astra_updates
        self.lon,self.lat=grid(c['bounds'],c['grid_km']);self.shape=self.lon.shape
        detail_relief=getattr(height,'relief',None);detail_peak=getattr(height,'peak',None);detail_cover=getattr(height,'coverage',None)
        detail_land=getattr(height,'land_fraction',None)
        height=np.asarray(height,dtype='float32')
        if height.shape!=self.shape or not np.isfinite(height).all(): raise ValueError('DEM and model grid do not match')
        self.land=height>0 if detail_land is None else np.asarray(detail_land)>=.5
        self._land_fraction=(np.clip(np.asarray(detail_land,dtype=float),0,1)
                             if self.astra_updates and detail_land is not None else None)
        self.h=np.maximum(height,0)*(1 if c['terrain'] else 0)
        self.terrain_relief=np.zeros(self.shape) if detail_relief is None else np.asarray(detail_relief)*c['terrain']
        self.terrain_peak=self.h.copy() if detail_peak is None else np.asarray(detail_peak)*c['terrain']
        self.terrain_cover=np.zeros(self.shape) if detail_cover is None else np.asarray(detail_cover)*c['terrain']
        # Neutral log-law roughness: generic land/sea + unresolved relief,
        # not a claim that this DEM contains vegetation/urban land-cover data.
        sigma=max(.5,12/c['grid_km']);smooth=gaussian_filter(self.h,sigma)
        relief=np.sqrt(np.maximum(gaussian_filter(self.h**2,sigma)-smooth**2,0)+self.terrain_relief**2)
        land_z0=.08+.25*np.clip(relief/400,0,1)
        self.land_surface_cd=(.4/np.log((Z[0]+land_z0)/land_z0))**2
        self.surface_z0=self.land_cover*land_z0+(1-self.land_cover)*.0002
        self.surface_cd=(self.land_cover*self.land_surface_cd
                         +(1-self.land_cover)*(.4/np.log((Z[0]+.0002)/.0002))**2)
        # Legacy branch only: never clip live Astra/Sol CAPE to a latitude
        # lookup. Such clipping painted a zonally uniform high-CAPE ribbon.
        # The current branch puts its northward stability/moisture gradient
        # into actual INITIAL soundings, which subsequently move with air.
        self.cape_ceiling=40+3560/(1+np.exp((self.lat-23.3)/.4))
        self.dx=c['grid_km']*1000;self.time=0.;self.steps=0
        seeds=np.random.SeedSequence(int(c['seed'])).spawn(5)
        self.rngs=[np.random.default_rng(s) for s in seeds]
        self.seed_ids=[int(s.generate_state(1)[0]) for s in seeds]
        self.noise=correlated(self.rngs[2],self.shape, max(3,40/c['grid_km']))
        self.cell_noise=correlated(self.rngs[4],self.shape,max(1,14/c['grid_km']))
        self.day_noise=correlated(self.rngs[3],self.shape,max(3,180/c['grid_km']))
        initial=correlated(self.rngs[0],self.shape,max(3,65/c['grid_km']))
        humidity=correlated(self.rngs[1],self.shape,max(3,50/c['grid_km']))
        self.synoptic=SynopticDriver(c,self.lon,self.lat,self.h)
        # External reservoir starts NORTH of the domain; the internal tracer
        # enters by open-boundary transport, never by resetting a rain mask.
        front=25.05+.12*np.sin((self.lon-109)*1.3)+.08*initial
        self.air=(self.synoptic.external_air() if self.astra_updates else
                  1/(1+np.exp(np.clip(-(self.lat-front)*111195/18000,-40,40)))).astype('float32')
        self.ps=(101000*np.exp(-self.h/8200)).astype('float32')
        z=Z[:,None,None];self.p=(self.ps[None]*np.exp(-z/8000)).astype('float32')
        self.mass=(self.ps[None]*np.exp(-z/8000)/(RD*(288-z*.005))*DZ[:,None,None]).astype('float32')
        # U0 controls a shallow wind-shape, not only one independent level.
        # Distribute ONE surface stress over exactly that shape's air mass.
        shallow=np.exp(-(Z-Z[0])/650)[:,None,None]
        self.surface_mixed_mass=np.sum(self.mass*shallow,axis=0)
        free_surface=299+(c['month']-4)*1.1-self.h*.005-.2*(self.lat-23)+initial*.6
        surface=self.land_cover*free_surface+(1-self.land_cover)*(c['sst_c']+273.15)
        lapse=.0063+(.00025*humidity)[None]
        # A cold spring sea cools the MARINE boundary layer, not the whole
        # troposphere. Cooling every level preserved artificial offshore CAPE.
        cold_column=self.frontal_layers() if self.astra_updates else self.air[None]
        self.temp=(free_surface[None]+(surface-free_surface)[None]*np.exp(-z/850)
                   -np.minimum(z,11500)*lapse-np.maximum(z-11500,0)*.0008
                   +2.2*np.exp(-((z-1300)/450)**2)-(9 if self.astra_updates else 7)*cold_column*np.exp(-z/2000 if self.astra_updates else -z/1400)).astype('float32')
        north=.5*(1+np.tanh((self.lat-24.0-.15*initial)/.9))
        if self.astra_updates:
            self.temp+=2.5*north[None]*np.exp(-((z-1500)/800)**2)
        self.radiative_reference=self.temp.copy()
        td=294.5+(c['month']-4)*1.0+(c['moisture']-1)*13-self.h*.0018+humidity*.65-3*self.air
        qs=saturation(np.minimum(td,surface-1),self.ps)
        self.q=(qs[None]*np.exp(-np.maximum(z-850,0)/2300)).astype('float32')
        humidity_floor=.55+self.MIDLEVEL_HUMIDITY_BOOST*np.exp(-((z-5500)/3300)**2)
        self.q=np.maximum(self.q,saturation(self.temp,self.p)*np.clip(humidity_floor*c['moisture'],.3,.88)*np.exp(-np.maximum(z-9000,0)/2000))
        if self.astra_updates:self.q*=np.exp(-.65*north[None]*np.exp(-z/3200))
        self.q=np.minimum(self.q,saturation(self.temp,self.p)*.98)
        # Optional memory/bandwidth mode: same grid, physics, stability steps
        # and float64 parcel diagnostics; only volume water storage is float32.
        # Default stays float64. Keep audits in double precision in this mode.
        if c['compact_transport']:self.q=self.q.astype('float32')
        # Incoming synoptic air carries its own heat/water reservoir. Copying
        # the progressively depleted edge cell into inflow ghosts recycled
        # dry, convectively processed air instead of replenishing the LLJ.
        self.inflow_q=self.q.copy();self.inflow_air=self.air.copy()
        # A finite wet-soil skin cannot jump back to a prescribed sunny-land
        # temperature immediately after rain. Its energy budget is separate
        # from atmospheric sensible/latent exchange.
        # The land skin is a patch temperature, not the sea/land mean air.
        # Its finite heat capacity and flux are weighted by its area below.
        self.ground_temp=(self.temp[0]+(self.land_cover>0)*(free_surface-surface)*np.exp(-Z[0]/850)).astype('float32')
        self.ground_reference=self.ground_temp.copy()
        self.cloud=np.zeros_like(self.q);self.rain=np.zeros_like(self.q)
        self.anvil=np.zeros_like(self.q)  # detrained, slow-falling frozen water
        # Signed, water-weighted source orientation and normal outflow speed.
        # Transport these WITH the ice. A decayed parent updraft must not turn
        # its already detrained rearward cloud back into ambient forward flow.
        self.anvil_nx=np.zeros_like(self.q);self.anvil_ny=np.zeros_like(self.q)
        self.anvil_motion=np.zeros_like(self.q)
        self.anvil_convective=np.zeros_like(self.q)  # origin subset, NOT extra water
        self.anvil_number=np.zeros_like(self.q)  # crystals / kg dry air, not water
        self.convective_ice_source=0.;self.environmental_ice_source=0.
        self.graupel=np.zeros_like(self.q);self.graupel_area=np.zeros_like(self.q)
        # Two-way downdraft momentum exchange; the reference wind aloft is
        # not an inexhaustible source which can be copied to the surface.
        self.momentum_u=np.zeros_like(self.q);self.momentum_v=np.zeros_like(self.q)
        self.downburst_energy=np.zeros(self.shape);self.downburst_area=np.ones(self.shape)
        self.downdraft_mass_depth=np.zeros(self.shape)
        self.cold_head_dissipation=0.
        self.plume_water_supplied=0.;self.plume_water_requested=0.;self.rain_water_evaporated=0.
        self.gust_peak=0.;self.meanwind_peak=0.
        self.stratiform_rain=np.zeros_like(self.q)  # a SUBSET of rain, not water twice
        # A subset of cloud, NOT additional water. Carry its origin through
        # advection so a mature plume is not erased when it enters a grid cell
        # whose instantaneous trigger has already switched off.
        self.plume_cloud=np.zeros_like(self.q)
        self.plume_cloud_area=np.zeros_like(self.q)
        self.plume_rain=np.zeros_like(self.q)
        self.rain_area=np.zeros_like(self.q)  # diagnostic moment, NOT water
        self.total=np.zeros(self.shape,dtype='float32');self.cold=self.total.copy();self.lift=self.total.copy();self.activity=self.total.copy()
        self.cold_depth=self.total.copy();self.cold_content=self.total.copy()
        self.cold_mx=self.total.copy();self.cold_my=self.total.copy();self.cold_max_cfl=0.
        self.cold_source=0.;self.cold_external=0.;self.cold_recovery=0.
        self.last_rate=self.total.copy();self.w=self.total.copy();self.initiation=self.total.copy();self.gust_lift=self.total.copy()
        self.last_core_rate=self.total.copy()
        self.last_stratiform_rate=self.total.copy()
        # Unresolved convective adjustment follows low-level processed air,
        # not the radar echo. Switching MU layers cannot reset a worked column.
        self.cape_deficit=self.total.copy()
        self.cape_consumed=0.;self.cape_recovered=0.
        self.synoptic_lift=self.total.copy();self.background_w=self.total.copy()
        self.rain_history=[(0.,self.total.copy())];self.next_rain_history=300.
        self.surface_rain=SurfaceRain(self.shape,c['seed'])
        self.ascent_depth=np.full(self.shape,3500.)
        self.front_advance=self.total.copy()
        self.organization=self.total.copy();self.plume_fraction=np.full(self.shape,.035,dtype='float32')
        self.surface_activity=self.total.copy()  # origin subset of activity
        self.donors=np.arange(self.lon.size).reshape(self.shape)
        # Start in the background flow, not a domain-wide southerly spin-up
        # which immediately carries the initial cold reservoir northward.
        self.u=(4*(1-self.air)+self.air).astype('float32')
        # Balance the initial meridional inflows at the Nanling transition.
        # Strengthening only the warm southerly made this a retreating warm
        # front. The northern surge remains an independent later forcing.
        self.v=(5*c['jet']*(1-self.air)-(5*c['jet']+.5)*self.air).astype('float32')
        # The deep synoptic cold reservoir and a shallow convective outflow
        # are different air masses. A shallow rain-cooled gust must not advect
        # the whole 1.4 km reservoir as though it were the same surface tracer.
        self.syn_u=self.u.copy();self.syn_v=self.v.copy()
        self.trough_lon=(self.synoptic.bay_lon if self.astra_updates else 104.7+float(self.rngs[3].uniform(-.5,.5)))
        self.north_trough_lon=94.5+float(self.rngs[3].uniform(-1,1))
        self.upper_angle=math.radians(float(self.rngs[3].uniform(-8,18)))
        # The southern and northern disturbances have distinct geometry and
        # phase speeds. A fast cloud steering wind is NOT a front speed.
        self.north_phase_speed=float(self.rngs[3].uniform(.26,.34))
        # Independent stream: regional pressure-wave geometry is not always
        # a western wave. It does not consume the existing cell/noise streams.
        front_rng=np.random.default_rng(np.random.SeedSequence([int(c['seed']),3917]))
        self.front_regime=['coupled','west','east','mixed'][int(front_rng.integers(4))]
        self.front_phase=float(front_rng.uniform(-1,1))
        if self.astra_updates:
            self.u,self.v=[a.astype('float32') for a in self.synoptic.surface_target(self.air,0)]
            self.syn_u=self.u.copy();self.syn_v=self.v.copy()
        self.trough_strength=c['trough'];self.next_noise=900;self.next_cell_noise=300;self.next_day_noise=21600;self.next_diagnostic=0
        self.initial_water=float(np.sum((self.q+self.cloud+self.rain)*self.mass,dtype='float64' if c['compact_transport'] else None))
        self.external_water=0.;self.frontal_exchange_water=0.;self.numerical_water=0.;self.max_cfl=0.;self.audit=[]
        self.diagnostics()
        if self.astra_updates:
            self.synoptic.configure_genesis(self.mu['cape'],self.mu['cin'],self.mu_lfc,self.h)
        self.genesis_closed=False
        self.genesis_started=False
        self.convective_day=0
        self.next_genesis_check=1800.

    @property
    def land_cover(self):
        # Keep caller-supplied binary DEMs (and the legacy branch) binary;
        # actual coastal DEM moments retain their continuous land coverage.
        return self.land if self._land_fraction is None else self._land_fraction

    def frontal_layers(self,air=None):
        """A 1:120 cold wedge, based on the advected surface air tracer.

        This diagnoses the sloping frontal surface, not a rain/echo mask.
        Warm air can overrun a shallow cold surface at 0.6--3 km AGL.
        """
        air=self.air if air is None else air
        logit=np.log(np.clip(air,1e-7,1-1e-7)/np.clip(1-air,1e-7,1))
        return 1/(1+np.exp(np.clip(-logit[None]+(Z[:,None,None]-Z[0])*120/18000,-40,40)))

    def frontal_drift(self):
        """Slow, locally undulating background flow; no frozen-front timer."""
        if not self.astra_updates:return np.zeros(self.shape)
        wave=.45+.35*np.tanh(self.day_noise)+.2*np.sin((self.lon-self.trough_lon)/2.5)
        return wave*np.exp(-((self.air-.5)/.3)**2)

    def synoptic_surge(self):
        if not self.astra_updates:
            return np.exp(-((self.lon-self.north_trough_lon)/3)**2)*self.cfg['cold_reservoir']
        # Phase of the evolving northern disturbance sets the common envelope;
        # seeded pressure lobes set regional leads/lags. Every pattern retains
        # a broad component, so Guangdong is not permanently left unforced.
        envelope=math.exp(-((111.2+self.front_phase-self.north_trough_lon)/3)**2)
        if self.front_regime=='coupled':pattern=.9+.1*np.tanh(self.day_noise)
        elif self.front_regime=='west':pattern=.6+.65*np.exp(-((self.lon-108-self.front_phase)/3.8)**2)
        elif self.front_regime=='east':pattern=.6+.65*np.exp(-((self.lon-114.5-self.front_phase)/3.8)**2)
        else:pattern=.55+.7*(.5+.5*np.cos((self.lon-111-self.front_phase)/1.7))
        return envelope*pattern*self.cfg['cold_reservoir']

    def winds(self):
        z=Z[:,None,None];c=self.cfg
        if self.astra_updates:
            free_u,free_v,jet_u,jet_v=self.synoptic.free_winds(z,self.time,self.trough_lon,self.day_noise)
            blend=1-np.exp(-(z-Z[0])/1500)
            shallow=np.exp(-(z-Z[0])/650)
            u=self.syn_u[None]*(1-blend)+free_u*blend+(self.u-self.syn_u)[None]*shallow
            v=self.syn_v[None]*(1-blend)+free_v*blend+(self.v-self.syn_v)[None]*shallow
            jet_weight=(1-np.exp(-(z-Z[0])/250))*(1-self.frontal_layers())
            u+=jet_u*jet_weight+self.momentum_u;v+=jet_v*jet_weight+self.momentum_v
            return u.astype('float32'),v.astype('float32')
        # Inland thermals favour afternoon initiation; the nocturnal coastal
        # LLJ can still sustain morning rain. This is not a daytime rain mask.
        hour=(8+self.time/3600)%24
        nocturnal=.90+.25*math.cos((hour-4)*2*math.pi/24)
        jet=14*c['jet']*nocturnal*np.exp(-((z-1000)/700)**2)
        upper_jet=18*c['shear']*np.exp(-((z-10500)/3300)**2)*(1+.1*np.tanh(self.lat-24))
        free_u=7+z*.0025*c['shear']+upper_jet
        free_v=free_u*math.tan(self.upper_angle)*(1-np.exp(-z/4000))
        # Earth-relative layered steering, not a shared storm translation speed.
        blend=1-np.exp(-(z-Z[0])/1500)
        shallow=np.exp(-(z-Z[0])/650)
        u=self.syn_u[None]*(1-blend)+free_u*blend+(self.u-self.syn_u)[None]*shallow
        v=self.syn_v[None]*(1-blend)+free_v*blend+(self.v-self.syn_v)[None]*shallow
        # A boundary-layer jet must not be halved by the background/free-air
        # blending. Keep it zero at the lowest level, retain a southerly moist
        # feed above that level, and taper it over the cold synoptic air mass.
        cold_column=self.frontal_layers() if self.astra_updates else self.air[None]
        jet_weight=(1-np.exp(-(z-Z[0])/250))*(1-cold_column)
        u+=jet*.50*jet_weight;v+=jet*.90*jet_weight
        wave=np.exp(-((self.lon-self.trough_lon)/2)**2)*np.exp(-((z-5500)/4000)**2)
        v=v+6*self.trough_strength*wave*np.tanh(self.lon-self.trough_lon)*blend
        if self.astra_updates:
            u+=self.momentum_u;v+=self.momentum_v
        return u.astype('float32'),v.astype('float32')

    def resolved_ascent(self,u,v):
        base=self.w[None]*np.exp(-Z[:,None,None]/self.ascent_depth[None])
        if not self.astra_updates:return base
        # The environmental/front lift and a shallow outflow circulation do
        # NOT have the same vertical reach. Extending residual 50--150 m
        # cold-layer convergence through the warm column's 3.5 km scale kept
        # manufacturing low/mid-level liquid cloud long after its storm left.
        # Strong head plumes still use their independent finite mass flux.
        head_depth=maximum_filter(self.cold_depth,size=3,mode='nearest')
        outflow=self.w-self.background_w
        reach=np.maximum(2*head_depth,150)
        base=self.background_w[None]*np.exp(-Z[:,None,None]/self.ascent_depth[None])
        base+=outflow[None]*np.minimum(head_depth/1000,1.8)[None]*np.exp(-Z[:,None,None]/reach[None])
        ay,ax=np.gradient(gaussian_filter(self.air,max(.5,12/self.cfg['grid_km'])),self.dx)
        length=np.maximum(np.hypot(ax,ay),1e-12)
        nx=ax/length;ny=ay/length
        cold_column=self.frontal_layers()
        # Cross-front flow relative to the evolving surface contour. Westerly
        # winds still advect condensate eastward; the front need not move east.
        front_normal=self.syn_u*nx+self.syn_v*ny
        crossing=np.maximum(u*nx[None]+v*ny[None]-front_normal[None],0)
        slope_ascent=crossing/120*4*cold_column*(1-cold_column)
        slope_ascent*=np.exp(-np.maximum(Z[:,None,None]-3500,0)/1800)
        stationary=4*self.air*(1-self.air)*(1-self.front_advance)
        # Keep shallow convergence in the trigger/displacement budget, but do
        # not turn it into a deep, stationary condensate curtain at air=.5.
        base=base*(1-stationary[None])
        return np.clip(base+slope_ascent,-.4,.8)

    def diagnostics(self):
        self.sb=parcel(self.p,self.temp,self.q,'surface')
        self.mu=parcel(self.p,self.temp,self.q,'unstable')
        diagnosed=np.maximum(self.mu['cape'],0)
        if not self.astra_updates:diagnosed=np.minimum(diagnosed,self.cape_ceiling)
        self.cape_capacity=np.maximum(getattr(self,'cape_capacity',diagnosed),diagnosed)
        self.lfc=free_convection_height(self.sb,self.temp,self.q,self.p)
        self.mu_lfc=free_convection_height(self.mu,self.temp,self.q,self.p)
        # A cold, stable surface may have large elevated MU CAPE. It must not
        # feed the same broad deep mass flux as an attached warm-sector PBL.
        coupling=np.clip(self.sb['cape']/np.maximum(self.mu['cape'],100),0,1)
        # Even a 650–1000 m source can be detached from a stable frontal PBL.
        # The old height taper and donor-only support effectively treated it
        # as a fully warm column. Advancing frontal forcing can reconnect it;
        # stalled, stable columns retain only limited elevated mass flux.
        self.deep_support=1-.94*self.air*(1-coupling)*(1-.65*self.front_advance)
        pq=np.minimum(self.mu['source_mixing_ratio'][None],saturation(self.mu['path'],self.p))
        buoyancy=np.maximum(virtual(self.mu['path'],pq)-virtual(self.temp,self.q),0)
        cloud_layer=(self.p<self.mu['lcl_pressure'][None])&(self.p>=30000)
        cloud_top=np.max(np.where((buoyancy>0)&cloud_layer,Z[:,None,None],0),axis=0)
        source_height=Z[self.mu['start_index']]
        self.plume_depth=np.clip(cloud_top-source_height,1000,15000)
        source_temp=np.take_along_axis(self.temp,self.mu['start_index'][None],axis=0)[0]
        self.cape_response=G*np.clip(cloud_top-source_height,2000,10000)/np.maximum(source_temp,240)
        # Translate OLD cells by cloud-bearing middle/upper winds. A frontal
        # envelope moves south by NEW initiation; it is not that same velocity.
        weights=buoyancy*self.mass*cloud_layer*np.clip(Z[:,None,None]/3500,.3,2)
        fallback=self.mass*((self.p<=85000)&(self.p>=30000))
        self.steering_weights=np.where((weights.sum(axis=0)>1e-6)[None],weights,fallback)
        self.next_diagnostic=self.time+900

    def steering(self,u,v):
        """Approximate existing-cell advection by its buoyant cloud layer.

        System propagation still emerges from NEW initiation along outflow;
        do not add a prescribed Corfidi displacement to that same process.
        This does not represent rotating-supercell deviant motion.
        """
        weights=self.steering_weights;denominator=np.maximum(weights.sum(axis=0),1e-9)
        return (u*weights).sum(axis=0)/denominator,(v*weights).sum(axis=0)/denominator

    def storm_motion(self,u,v):
        """Translate the convective pattern, not the environmental air.

        The middle-level transport is already calibrated in free_winds.
        Retain 70% of its warm-sector pattern steering; front-attached cells
        retain the full local cloud-layer translation. The upper jet is not
        reduced; cold-pool propagation still uses the active-layer solver.
        """
        cu,cv=self.steering(u,v)
        if not self.astra_updates:return cu,cv
        frontal=np.clip((self.air-.1)/.4,0,1)
        retained=self.WARM_PATTERN_RETENTION+(1-self.WARM_PATTERN_RETENTION)*frontal
        return cu*retained,cv*retained

    def available_cape(self,raw):
        """Available model energy, distinct from uncapped parcel CAPE."""
        if not self.astra_updates:return np.maximum(np.minimum(np.maximum(raw,0),self.cape_ceiling)-self.cape_deficit,0)
        # Resolved drying/heating already lowers parcel energy. Limit by the
        # remaining column budget, do not subtract that SAME stabilization
        # again from the newly diagnosed depleted sounding.
        remaining=np.maximum(self.cape_capacity-self.cape_deficit,0)
        return np.minimum(np.maximum(raw,0),remaining)

    def plume_reservoir(self):
        source=self.mu['start_index']
        pressure=np.take_along_axis(self.p,source[None],axis=0)[0]
        supply=(np.abs(Z[:,None,None]-Z[source][None])<=1000)&(np.abs(self.p-pressure[None])<=15000)
        return supply,np.sum(np.where(supply,self.mass,0),axis=0)

    def transport_cape_budget(self,dt,u,v):
        # The diagnosed deficit represents unresolved column stabilization
        # and the low-level wake, not a parcel traveling with a new MU layer.
        warm=np.maximum(advect(self.cape_deficit,u[0],v[0],dt,self.dx,boundary=0),0)
        if hasattr(self,'transported_wake_debt'):
            # Active density currents no longer move at the background wind.
            # Carry processed-air memory on EXACTLY their depth/momentum flux,
            # otherwise fresh low-debt air numerically washes through a cold
            # wake and looks like rapid CAPE recovery without a heat source.
            warm=np.where(self.cold_depth>100,self.transported_wake_debt,warm)
        self.cape_deficit=warm
        if self.astra_updates:
            capacity=np.maximum(advect(self.cape_capacity,u[0],v[0],dt,self.dx,boundary=np.maximum(self.mu['cape'],0)),0)
            if hasattr(self,'transported_wake_capacity'):capacity=np.where(self.cold_depth>100,self.transported_wake_capacity,capacity)
            self.cape_capacity=capacity

    def recover_cape_budget(self,heat,water,connection=1.):
        """Boundary enthalpy flux restores energy; no fixed wake timeout.

        Heat is kg K/m2 and water kg/m2 actually entering the source column.
        This is a reduced CAPE-adjustment closure, not total-energy dynamics.
        """
        _,air_mass=self.plume_reservoir()
        # Net moist enthalpy, not two independently positive credits. A
        # detached MU layer cannot instantly receive a flux below a stable cap.
        gain=self.cape_response*np.maximum(heat+LV/CP*water,0)*connection/np.maximum(air_mass,1)
        recovered=np.minimum(self.cape_deficit,gain)
        self.cape_deficit-=recovered;self.cape_recovered+=float(recovered.sum())

    def surface_cape_connection(self,u,v):
        theta=virtual(self.temp,self.q)*(100000/self.p)**(RD/CP)
        height=Z[:,None,None]-Z[0]
        ri=G*np.maximum(theta-theta[:1],0)*height/(np.maximum(theta[:1],200)*(
            (u-u[:1])**2+(v-v[:1])**2+4))
        reachable=np.minimum.accumulate(np.clip(1-ri/.25,0,1),axis=0)
        return np.take_along_axis(reachable,self.mu['start_index'][None],axis=0)[0]

    def surface_exchange(self,dt,solar,sun):
        density=self.mass[0]/DZ[0];wind=np.maximum(np.hypot(self.u,self.v),2)
        # Bulk coefficients, finite soil heat capacity and rainwater sensible
        # cooling. Radiation enters the SOIL; no second imposed air heating.
        transfer=density*.0015*wind
        qground=saturation(self.ground_temp-2,self.ps)*self.cfg['moisture']
        land_evap=transfer*(qground-self.q[0])
        sensible=CP*transfer*(self.ground_temp-self.temp[0])
        wetbulb=np.minimum(self.temp[0],dewpoint(self.q[0],self.p[0])+2)
        rain_cooling=self.last_rate/3600*4186*np.maximum(self.ground_temp-wetbulb,0)
        radiation=420*solar-35*(1-sun)
        soil=15*(self.ground_temp-self.ground_reference)
        ground_change=dt*(radiation-sensible-LV*land_evap-soil-rain_cooling)/200000
        self.ground_temp+=ground_change*(self.land_cover>0)
        land_heat=sensible*dt/(CP*self.mass[0])
        sea_heat=(self.cfg['sst_c']+273.15-self.temp[0])*dt/(1800/np.maximum(wind/5,1))
        heat=self.land_cover*land_heat+(1-self.land_cover)*sea_heat
        sea_q=saturation(self.cfg['sst_c']+271.15,self.ps)*self.cfg['moisture']
        exchange=(self.land_cover*land_evap*dt/self.mass[0]
                  +(1-self.land_cover)*(sea_q-self.q[0])*dt/18000)
        self.temp[0]+=heat;self.q[0]+=exchange
        self.external_water+=float(np.sum(exchange*self.mass[0],dtype='float64' if self.cfg['compact_transport'] else None))
        return heat,exchange,self.land_cover*self.ground_temp+(1-self.land_cover)*(self.cfg['sst_c']+273.15)

    def upstream_environment(self):
        """Fresh thermodynamic supply follows the evolving boundary air mass.

        A fixed initial frontal latitude at the west/east ghost cells would
        inject warm air behind a departed front and split it into new contours.
        The tracer remains open; external heat/moisture follow its local
        synoptic cold fraction rather than resetting the front's position.
        """
        boundary_air=self.synoptic.external_air() if self.astra_updates else self.air
        changed=boundary_air-self.inflow_air
        if self.astra_updates:
            cold_change=self.frontal_layers(boundary_air)-self.frontal_layers(self.inflow_air)
            t=self.radiative_reference-9*cold_change*np.exp(-Z[:,None,None]/2000)
        else:t=self.radiative_reference-7*changed[None]*np.exp(-Z[:,None,None]/1400)
        if self.astra_updates:
            q=self.inflow_q*np.exp(-.55*cold_change+.08*self.cfg['stochastic']*self.day_noise[None]*np.exp(-Z[:,None,None]/1800))
        else:q=self.inflow_q*np.exp((-.22*changed+.08*self.cfg['stochastic']*self.day_noise)[None]*np.exp(-Z[:,None,None]/1800))
        return t,np.minimum(q,saturation(t,self.p)*.98)

    def transport_front_thermodynamics(self,old_layers,new_layers,layer_adv,dt):
        """Carry frontal heat/moisture with the SAME material cold-air front.

        Layer steering and the shallow synoptic reservoir have different
        velocities. Account for their exchanged air-mass fraction, not a
        relaxation of every cold cell to a reference sounding each step.
        Existing convective anomalies survive when the fraction is unchanged.
        This is an explicitly audited reduced-model air-mass exchange.
        """
        boundary=self.frontal_layers(self.synoptic.external_air())
        transported=np.clip(layer_adv(old_layers,dt,boundary=boundary),0,1)
        delta=new_layers-transported
        incoming_cold=np.clip(delta/np.maximum(1-transported,1e-6),0,1)
        incoming_warm=np.clip(-delta/np.maximum(transported,1e-6),0,1)
        # No source is applied to a uniform material air mass. In particular,
        # a fully postfrontal column cannot regenerate a warm MU reservoir by
        # repeated copying of its prefrontal reference at a ghost boundary.
        cold_t=self.radiative_reference-9*(1-self.frontal_layers(self.inflow_air))*np.exp(-Z[:,None,None]/2000)
        cold_q=self.inflow_q*np.exp(-.55*(1-self.frontal_layers(self.inflow_air)))
        cold_q=np.minimum(cold_q,saturation(cold_t,self.p)*.95)
        old_q=self.q.copy()
        self.temp+=incoming_cold*(cold_t-self.temp)+incoming_warm*(self.radiative_reference-self.temp)
        self.q+=incoming_cold*(cold_q-self.q)+incoming_warm*(self.inflow_q-self.q)
        self.external_water+=float(np.sum((self.q-old_q)*self.mass,dtype='float64'))
        self.frontal_exchange_water+=float(np.sum((self.q-old_q)*self.mass,dtype='float64'))

    def cold_diagnostics(self):
        self.cold=np.maximum(self.cold_content,0)/np.maximum(self.cold_depth,30)

    def cold_surface_coupling(self,dt):
        active=self.cold**2/(self.cold**2+.35**2)
        return (1-np.exp(-self.cold_depth/180))*active*(-math.expm1(-dt/90))

    def drag_coefficient(self,speed):
        cd=self.surface_cd.copy()
        if np.any(self.land_cover<1):
            # Two bulk Charnock iterations: sea stress must also strengthen
            # in high winds; a permanently glassy-water roughness is unsafe.
            sea_cd=np.full_like(speed,(.4/np.log((Z[0]+.0002)/.0002))**2,dtype=float)
            for _ in range(2):
                z0=.0002+.018*sea_cd*speed**2/G
                sea_cd=(.4/np.log((Z[0]+z0)/z0))**2
            cd=self.land_cover*self.land_surface_cd+(1-self.land_cover)*sea_cd
        return cd

    def surface_friction(self,dt):
        """Quadratic surface stress, integrated without reversing the wind.

        Two half steps surround momentum sources. Distribute stress over the
        model's shallow wind shape, without adding an opposite anomaly aloft
        which would accumulate into an artificial jet over repeated steps.
        The lowest wind is about 30 m AGL, NOT an exact 10-m observation.
        """
        speed=np.hypot(self.u,self.v)
        rho0=self.mass[0]/DZ[0]
        retained=1/(1+self.drag_coefficient(speed)*speed*dt*rho0/self.surface_mixed_mass)
        self.u*=retained;self.v*=retained

    def transport_cold_pool(self,dt):
        """Active-layer pressure drives expansion even in a still atmosphere."""
        debt=self.cold_depth*self.cape_deficit
        if self.astra_updates:
            # Boundary organization belongs to the active density current,
            # not the slower frictional surface wind. Carry its finite-volume
            # moment with exactly the same head flux, including wet/dry faces.
            tracers=np.stack([debt,self.cold_depth*self.cape_capacity,
                              self.cold_depth*self.organization])
            self.cold_depth,self.cold_content,self.cold_mx,self.cold_my,debt,capacity,organized,external,cfl=advance_cold_pool(
                self.cold_depth,self.cold_content,self.cold_mx,self.cold_my,self.h,dt,self.dx,tracer=tracers,higher_order=True)
            self.transported_wake_capacity=np.maximum(capacity/np.maximum(self.cold_depth,1e-9),0)
            self.organization=np.clip(organized/np.maximum(self.cold_depth,1e-9),0,1)
        else:
            self.cold_depth,self.cold_content,self.cold_mx,self.cold_my,debt,external,cfl=advance_cold_pool(
                self.cold_depth,self.cold_content,self.cold_mx,self.cold_my,self.h,dt,self.dx,tracer=debt,higher_order=False)
        self.transported_wake_debt=np.maximum(debt/np.maximum(self.cold_depth,1e-9),0)
        self.cold_external+=external;self.cold_max_cfl=max(self.cold_max_cfl,cfl)
        # Exchange momentum with the reference atmosphere, plus surface drag.
        # Pressure acceleration already occurs in the finite-volume solver;
        # do NOT apply it a second time to the background surface wind.
        cu,cv=cold_velocity(self.cold_depth,self.cold_mx,self.cold_my)
        weight=-math.expm1(-dt/7200)
        self.cold_mx+=weight*self.cold_depth*(self.syn_u-cu)
        self.cold_my+=weight*self.cold_depth*(self.syn_v-cv)
        if self.astra_updates:self.cold_head_friction(dt)
        cu,cv=cold_velocity(self.cold_depth,self.cold_mx,self.cold_my)
        speed=np.hypot(cu,cv)
        drag=1+self.drag_coefficient(speed)*speed*dt/np.maximum(self.cold_depth,30)
        self.cold_mx/=drag;self.cold_my/=drag
        if self.astra_updates and np.any(self.terrain_relief):
            # Unresolved hills obstruct a shallow current even when their
            # cell-mean bed is low. Form drag removes momentum only; Q/H are
            # not erased and broad/deep currents can still cross the barrier.
            obstacle=2*self.terrain_relief
            ratio=obstacle/np.maximum(self.cold_depth,30)
            rate=.5*self.terrain_cover*ratio**2*speed/self.dx
            retained=1/(1+dt*rate)
            self.cold_mx*=retained;self.cold_my*=retained
        self.cold_diagnostics()

    def cold_head_friction(self,dt):
        """Finite ambient-fluid resistance at advancing density-current heads.

        A dry-bed shallow-water rarefaction alone treats ambient air as a
        vacuum. Dissipate outward relative momentum at the resolved head;
        never alter depth, cold content, interface geometry or set a speed.
        The reference atmosphere absorbs the pressure/form-drag reaction.
        """
        head=self.cold_head_pressure()
        hy,hx=np.gradient(head,self.dx);gradient=np.hypot(hx,hy)
        nx=-hx/np.maximum(gradient,1e-12);ny=-hy/np.maximum(gradient,1e-12)
        contact=np.clip(gradient*self.dx/np.maximum(maximum_filter(head,size=3),1),0,1)
        cu,cv=cold_velocity(self.cold_depth,self.cold_mx,self.cold_my)
        outward=np.maximum((cu-self.syn_u)*nx+(cv-self.syn_v)*ny,0)
        # Ambient resistance is not a shear-direction veto on cold AIR.
        # The former extra 1.5 x flank penalty arrested lateral head merging
        # between neighbouring rain shafts. Shear balance and ACTUAL inflow
        # already decide where that spreading air may make new deep plumes.
        # Keep finite head resistance, ground stress and real ridge drag;
        # do not suppress their common pressure boundary a second time.
        resistance=1.0
        retained=1/(1+resistance*contact*outward*dt/self.dx)
        impulse=outward*(1-retained)
        self.cold_mx-=self.cold_depth*impulse*nx;self.cold_my-=self.cold_depth*impulse*ny
        self.cold_head_dissipation+=float(np.sum(.5*self.cold_depth*(outward**2-(outward*retained)**2)))

    def cold_head_pressure(self,scale_km=12):
        # Diagnose the finite head at the shared inflow/plume scale, not at
        # each isolated rain shaft's pressure maximum. Grid-scale source
        # patches otherwise rotate the normal into a bow's receding flank
        # between adjacent cores and switch off their shared warm inflow.
        # This filtered diagnostic never changes prognostic Q/H, transports
        # cold air across dry gaps, or smooths cloud/rain/radar fields.
        return gaussian_filter(self.cold_content,max(.5,scale_km/self.cfg['grid_km']))

    def cold_head_normal(self,head):
        """Share boundary orientation, not the amplitude of each rain shaft.

        The pressure structure tensor identifies the local line's normal.
        An isolated circular pool has no preferred axis; a coherent boundary
        does. Its signed direction still comes from the actual pressure fall.
        This rotates with the weather and cannot impose a north--south line.
        """
        gy,gx=np.gradient(head,self.dx);length=np.hypot(gx,gy)
        nx=-gx/np.maximum(length,1e-10);ny=-gy/np.maximum(length,1e-10)
        sigma=max(.5,36/self.cfg['grid_km'])
        xx=gaussian_filter(gx*gx,sigma);yy=gaussian_filter(gy*gy,sigma)
        xy=gaussian_filter(gx*gy,sigma)
        angle=.5*np.arctan2(2*xy,xx-yy)
        tx,ty=np.cos(angle),np.sin(angle)
        sign=np.where(tx*nx+ty*ny>=0,1.,-1.)
        coherence=np.hypot(xx-yy,2*xy)/np.maximum(xx+yy,1e-20)
        weight=np.clip((coherence-.35)/.45,0,1)
        ax=(1-weight)*nx+weight*tx*sign;ay=(1-weight)*ny+weight*ty*sign
        magnitude=np.maximum(np.hypot(ax,ay),1e-10)
        return ax/magnitude,ay/magnitude

    def recover_cold_pool(self,dt,surface_heat,sun):
        before=float(self.cold_content.sum())
        self.cold_content=np.maximum(self.cold_content-np.maximum(surface_heat,0)*DZ[0],0)
        if self.astra_updates:
            # Turbulent exchange occurs for STRONG pools too, not only after
            # a six-hour exponential has finally made the layer neutral.
            # Shear and density-current turbulence compete with bulk Ri.
            cu,cv=cold_velocity(self.cold_depth,self.cold_mx,self.cold_my)
            u,v=self.winds()
            top=np.argmin(np.abs(Z[:,None,None]-self.cold_depth[None]),axis=0)
            tu=np.take_along_axis(u,top[None],axis=0)[0]
            tv=np.take_along_axis(v,top[None],axis=0)[0]
            shear=np.hypot(tu-cu,tv-cv)
            deficit=self.cold_content/np.maximum(self.cold_depth,30)
            pressure=G*self.cold_content/295
            ri=pressure/np.maximum(shear**2+pressure*.3,1)
            exchange_speed=.016*shear/np.sqrt(1+4*ri)+.005*np.sqrt(2*pressure)
            rate=1/21600+exchange_speed/np.maximum(self.cold_depth,100)
            self.cold_content*=np.exp(-dt*rate)
        else:
            tau=21600/(1+1.3*sun*self.land+.04*np.hypot(self.u,self.v))
            self.cold_content*=np.exp(-dt/tau)
        # A near-neutral remnant is detrained into the reference atmosphere,
        # NOT an ever-growing active density current. Remove depth, buoyancy,
        # and carried momentum in the SAME fraction (no temperature floor or
        # velocity impulse). Strong, replenished heads retain their pressure.
        deficit=self.cold_content/np.maximum(self.cold_depth,30)
        neutral=.35**2/(deficit**2+.35**2)
        speed=np.hypot(self.u,self.v);ustar=np.sqrt(self.drag_coefficient(speed))*speed
        mixing_time=np.clip(self.cold_depth/(.2+.3*ustar),900,3600)
        retained=np.exp(-dt*neutral/mixing_time)
        self.cold_depth*=retained;self.cold_content*=retained
        self.cold_mx*=retained;self.cold_my*=retained
        entrained=dt*(.006+.008*sun*self.land_cover)*(1-neutral)*(self.cold_content>1)
        self.cold_depth+=entrained
        self.cold_mx+=entrained*self.syn_u;self.cold_my+=entrained*self.syn_v
        overflow=np.maximum(self.cold_depth/1800,1)
        self.cold_content/=overflow;self.cold_depth=np.minimum(self.cold_depth,1800)
        self.cold_mx/=overflow;self.cold_my/=overflow
        retired=(self.cold_content<=.01)|(self.cold_depth<.01)
        self.cold_content=np.where(retired,0,self.cold_content)
        self.cold_depth=np.where(retired,0,self.cold_depth)
        self.cold_mx=np.where(self.cold_depth>0,self.cold_mx,0);self.cold_my=np.where(self.cold_depth>0,self.cold_my,0)
        self.cold_recovery+=before-float(self.cold_content.sum())
        self.cold_diagnostics()

    def supply_cold_pool(self,evaporation):
        # Cooling minus vapour's virtual-temperature compensation. Lower-level
        # downdrafts supply depth as well as heat deficit, not a fixed 650 m.
        cooling=evaporation[:6]*(LV/CP-.61*self.temp[:6])
        supplied=np.sum(cooling*DZ[:6,None,None],axis=0)
        wetbulb=np.sum(np.maximum(saturation(self.temp[:6],self.p[:6])-self.q[:6],0)
                       *(LV/CP-.61*self.temp[:6])*self.mass[:6],axis=0)/np.sum(self.mass[:6],axis=0)
        source_deficit=np.clip(wetbulb*.5,1.5,8)
        added_depth=supplied/source_deficit
        if self.astra_updates:
            # The shaft also supplies finite descending AIR, not just the
            # perfectly cold fraction Q / ambient wet-bulb potential. Mixing
            # that air spreads the same buoyancy loss through more volume.
            # No extra cooling, rainwater, prescribed footprint or heat sink.
            air_depth=np.minimum(self.downdraft_mass_depth,supplied/2.)
            added_depth=np.maximum(added_depth,air_depth)
        self.cold_content+=supplied;self.cold_depth+=added_depth
        self.cold_mx+=added_depth*self.u;self.cold_my+=added_depth*self.v
        self.cold_source+=float(supplied.sum())
        self.cold_diagnostics()

    def plume_environment(self,gust_lift,cell_u,cell_v,layer_u=None,layer_v=None):
        """Stable-layer and ridge-crossing cost of renewed plumes, not rain."""
        theta=virtual(self.temp,self.q)*(100000/self.p)**(RD/CP)
        n=np.sqrt(np.maximum(G*(theta[5]-theta[1])/(np.maximum(theta[1],200)*(Z[5]-Z[1])),1e-6))
        inhibition_step=np.maximum(self.donor_field(self.mu['cin'])-self.mu['cin'],0)
        connection=np.clip(self.sb['cape']/np.maximum(self.mu['cape'],100),0,1)
        incoming=np.maximum(self.donor_field(connection),self.surface_activity/np.maximum(self.activity,1e-9))
        # Surface-fed cells cannot instantly relabel themselves as elevated
        # storms on entering a stable sea layer. Carry their origin with them;
        # a genuinely elevated source is not charged this surface barrier.
        # Keep the finite surface-entry barrier separate from the deep energy
        # supply below; a cold surface must not erase truly elevated storms.
        marine_barrier=np.minimum(np.maximum(-self.sb['cin'],0),.5*n*n*850**2)
        # These two diagnostics describe the SAME marine entry barrier,
        # not two independent losses. A whole-column MU CIN difference is
        # not extra work across a finite shallow sea layer. Its actual CIN
        # still gates parcel activation elsewhere, including on the coast.
        marine_work=np.maximum(np.minimum(inhibition_step,marine_barrier),
                               np.maximum(incoming-connection,0)*marine_barrier)*(1-self.land_cover)
        if not self.astra_updates:
            marine_work=(inhibition_step+np.maximum(incoming-connection,0)*marine_barrier)*(~self.land)
        gy,gx=np.gradient(gaussian_filter(self.h,max(.5,8/self.cfg['grid_km'])),self.dx)
        speed=np.maximum(np.hypot(cell_u,cell_v),2)
        relief=np.abs((cell_u*gx+cell_v*gy)/speed)*18000
        if layer_u is None:layer_u,layer_v=self.winds()
        source_u=self.donor_field(np.take_along_axis(layer_u,self.mu['start_index'][None],axis=0)[0])
        source_v=self.donor_field(np.take_along_axis(layer_v,self.mu['start_index'][None],axis=0)[0])
        normal_flow=np.abs(source_u*gx+source_v*gy)/np.maximum(np.hypot(gx,gy),1e-9)
        # The barrier acts on warm low-level SUPPLY, not the much faster
        # cloud translation. Using cloud speed overstated ridge transmission.
        disruption=(n*relief/np.maximum(normal_flow,2))**2
        # The old 8-km-smoothed slope nearly erased Phoenix/Lantau/Tai Mo Shan.
        # Real fine-DEM height variance blocks only its covered fraction of
        # the low-level supply, not an entire model cell at its summit height.
        inflow_speed=np.hypot(source_u,source_v)
        disruption+=self.terrain_cover*(n*2*self.terrain_relief/np.maximum(inflow_speed,2))**2
        efficiency=np.exp(-marine_work/np.maximum(60+gust_lift*.1,1))/(1+disruption)
        return np.clip(efficiency,.02,1),np.minimum(5,disruption+marine_work/150)

    def plume_cape(self,fed_cape,sb_cape=None,mu_cape=None):
        """A surface-fed old cell cannot freely switch to offshore MU energy.

        New elevated cells and actual warm land donors keep their own energy.
        Only the lost surface-connected fraction loses unavailable SB CAPE;
        this changes water-producing mass flux, not the rendered radar colour.
        """
        sb=self.sb['cape'] if sb_cape is None else sb_cape
        mu=self.mu['cape'] if mu_cape is None else mu_cape
        source_sb=self.donor_field(sb)
        connection=np.clip(source_sb/np.maximum(self.donor_field(mu),100),0,1)
        origin=self.surface_activity/np.maximum(self.activity,1e-9)
        lost=np.clip(origin-connection,0,1)*(1-self.land_cover)
        # A genuinely fresh warm donor brings ITS energy over an exhausted
        # receiver at the leading edge. Do not subtract both columns' debts.
        adjusted=fed_cape-lost*np.maximum(fed_cape-source_sb,0)
        capacity=self.cape_capacity if self.astra_updates else self.cape_ceiling
        remaining=np.maximum(self.donor_field(capacity)-self.donor_field(self.cape_deficit),0)
        source_available=np.minimum(np.maximum(adjusted,0),remaining) if self.astra_updates else np.maximum(np.minimum(adjusted,self.donor_field(self.cape_ceiling))-self.donor_field(self.cape_deficit),0)
        return source_available if self.astra_updates else np.minimum(source_available,self.cape_ceiling)

    def elevated_displacement(self,source_height,gust_lift,head_depth):
        # A shallow density current cannot apply its full surface lift to a
        # 1–2 km elevated source merely because the ambient warm column has a
        # 3.5 km ascent scale. Synoptic lift and gust circulation have separate
        # vertical reaches; stronger/deeper cold pools can reach farther.
        return (self.synoptic_lift*np.exp(-source_height/self.ascent_depth)
                +gust_lift*np.exp(-source_height/np.maximum(2*head_depth,150)))

    def wake_fraction(self,source_height=0):
        # A cold interior is not a repeatedly liftable warm parcel. Truly
        # elevated parcels ABOVE the shallow layer retain independent ascent.
        return (1-np.exp(-self.cold/1.))*np.clip((self.cold_depth-source_height)/200,0,1)

    def fresh_initiation_air(self):
        # Depth alone is not a cold barrier: a 110-m, 0.3-K drizzle-cooled
        # layer was treated like a mature storm wake. Require BOTH a small
        # temperature deficit and small integrated negative buoyancy, while
        # retaining the transported convective energy-debt restriction.
        buoyancy_work=G*self.cold_content/295
        return ((self.air<.2)&(self.cold<1)&(buoyancy_work<10)
                &(self.cape_deficit<.35*np.maximum(self.cape_capacity,1)))

    def frontal_initiation_permission(self):
        """An advancing material front can initiate independently of a warm pulse.

        No CAPE or condensate is supplied here. The caller still applies the
        actual parcel LFC/CIN and available-energy tests. A uniform cold air
        mass, a stalled front, or a spent convective wake has no permission.
        """
        if not self.astra_updates:return np.zeros(self.shape)
        ay,ax=np.gradient(self.air,self.dx)
        transition=np.clip(np.hypot(ax,ay)*72000,0,1)
        advancing=np.clip((self.front_advance-.15)/.5,0,1)
        unused=(self.cape_deficit<.65*np.maximum(self.cape_capacity,1))
        unprocessed=(self.cold<1)&(G*self.cold_content/295<10)
        corridor=(self.air>.015)&(self.air<.85)
        return transition*advancing*corridor*unused*unprocessed

    def reconsider_genesis(self):
        """A later warm-sector episode needs new, actually favourable air.

        No per-day episode quota, no timed CAPE recovery and no wake reset.
        Recheck at sounding cadence after the earlier episode has finished;
        do not plant a second origin alongside its still-active mother line.
        """
        self.next_genesis_check=self.time+1800
        finished=(self.genesis_closed or self.synoptic.genesis_center is None
                  or self.time>=self.synoptic.genesis_start+self.synoptic.genesis_duration)
        if not finished:return False
        ongoing=(self.air<.2)&(self.activity>.1)&(self.last_rate>1)
        if ongoing.any():return False
        self.genesis_closed=True
        required=np.maximum(self.mu_lfc-Z[self.mu['start_index']],0)
        eligible=(self.fresh_initiation_air()&(self.available_cape(self.mu['cape'])>750)
                  &(self.mu['cin']>-75)&(required<2000)&(self.background_w>.005))
        if np.count_nonzero(eligible)*self.dx**2<max(2500e6,4*self.dx**2):
            self.synoptic.genesis_center=None
            return False
        self.synoptic.configure_genesis(self.available_cape(self.mu['cape']),self.mu['cin'],self.mu_lfc,self.h,
            fresh=eligible,episode=self.synoptic.episode_index+1,now=self.time)
        if self.synoptic.genesis_center is None:return False
        self.genesis_closed=False;self.genesis_started=False
        return True

    def trigger_perturbation(self,gust_lift):
        fluctuation=140*self.cfg['stochastic']*np.clip(self.cell_noise,-2,2)*(1-self.wake_fraction())
        if self.astra_updates:
            forcing=np.clip(np.maximum(self.background_w,0)/.08+gust_lift/500,0,1)
            fluctuation*=forcing*100/140
        return fluctuation

    def convective_head_edge(self,gradient,head_depth):
        """A filtered pressure gradient is not an already arrived cold head.

        Thin numerical tails may sense the neighbouring head, but cannot
        instantly apply its full lifting work a grid cell ahead. Recover full
        contact at a resolution-aware fraction of the actual head volume.
        Only plume coupling changes; no cold air or radar water is erased.
        """
        edge=np.clip(gradient/np.maximum(head_depth,100)*25000,0,1)
        if not self.astra_updates:return edge
        # A coarse finite-volume cell mixes the head with considerably more
        # warm air. Use its actual occupied volume, but do not impose the
        # fine-grid 15% threshold on a 28-km averaged head. Empty cells still
        # do no work: this is not permission to jump ahead of the current.
        occupancy=np.clip(.15*12000/self.dx,.05,.15)
        contact=np.sqrt(np.clip(self.cold_depth/np.maximum(head_depth,30)/occupancy,0,1))
        return edge*contact

    def warm_inflow(self,nx,ny,edge,balance):
        """Locate actual unprocessed air immediately ahead of an outflow.

        A coarse cell straddles cold downdraft and warm ascending inflow.
        Triggering both with the cold cell's sounding prevented regeneration.
        Donors are REAL columns along the outward normal. Try the nearest
        column first, then at most two cells (12 km on a 6-km grid). A mature
        finite-volume head can straddle two coarse cells: a fixed 12-km
        lookup then samples its own numerical cold tail indefinitely. Never
        skip an intervening ridge or an increasing cold-pressure peak. Shared
        donor air/water are explicitly debited, not copied per receiver.

        RKW balance controls subsequent lifting/work and organization, not
        whether this real warm column exists. Vetoing the donor here as well
        made oblique bow links fall back to their cold receiver's sounding,
        before their finite mechanical displacement could be evaluated.
        Positive storm-relative inflow and descendant lineage are still
        checked by the caller; finding a donor cannot initiate a plume.
        """
        y,x=np.indices(self.shape);distance=1.
        available=self.available_cape(self.mu['cape'])
        head=maximum_filter(self.cold_content,size=3,mode='nearest')
        donors=y*self.shape[1]+x;usable=np.zeros(self.shape,dtype=bool)
        for reach in sorted({distance,2.}):
            yy=np.clip(np.rint(y+ny*reach).astype(int),0,self.shape[0]-1)
            xx=np.clip(np.rint(x+nx*reach).astype(int),0,self.shape[1]-1)
            candidate=yy*self.shape[1]+xx
            cape=available.ravel()[candidate]
            content=self.cold_content.ravel()[candidate]
            depth=self.cold_depth.ravel()[candidate]
            cold=content/np.maximum(depth,30)
            ahead=(content<.35*np.maximum(head,1))&((depth<100)|(cold<.5))
            warmer=self.temp[0].ravel()[candidate]>self.temp[0]+.2
            valid=(edge>.08)&(cape>150)&ahead
            valid&=warmer|(cape>available+100)|(self.cold_content>content+100)
            valid&=np.abs(self.h.ravel()[candidate]-self.h)<500
            if reach>distance:
                my=np.clip(np.rint(y+ny*distance).astype(int),0,self.shape[0]-1)
                mx=np.clip(np.rint(x+nx*distance).astype(int),0,self.shape[1]-1)
                mid=my*self.shape[1]+mx
                middle=self.cold_content.ravel()[mid]
                valid&=(middle<=self.cold_content+1e-6)&(content<=middle+1e-6)
                valid&=np.abs(self.h.ravel()[mid]-self.h)<500
            donors=np.where(valid&~usable,candidate,donors)
            usable|=valid
        return donors,usable

    def donor_field(self,a):
        return np.asarray(a).reshape((-1,self.lon.size))[:,self.donors.ravel()].reshape(a.shape)

    def environmental_shear(self,u,v,head_depth=None):
        # RKW compares the cold current with ENVIRONMENTAL shear. Using the
        # accelerated outflow wind as the surface reference made a stronger
        # cold pool erase/reverse its own shear and shut down its leading line.
        attenuation=np.exp(-(Z[:,None,None]-Z[0])/650)
        ambient_u=u-(self.u-self.syn_u)[None]*attenuation
        ambient_v=v-(self.v-self.syn_v)[None]*attenuation
        # Fetch the whole warm-side environmental column FIRST. Interpolate
        # it at the RECEIVING head's lifting depth. Sampling an already
        # interpolated field instead used the donor's often absent cold-pool
        # depth, silently replacing deep-head shear with the 1500-m default.
        ambient_u=self.donor_field(ambient_u);ambient_v=self.donor_field(ambient_v)
        if head_depth is None:head_depth=maximum_filter(self.cold_depth,size=3,mode='nearest')
        # RKW compares the WIND DIFFERENCE across the lifting circulation,
        # not 3.2-km wind minus a jet-dominated layer MEAN. The latter reversed
        # the meridional shear as the pool deepened and rotated regeneration
        # onto huge southward flanks of an otherwise eastward-moving line.
        top=np.clip(2*head_depth,1500,3500)
        index=np.clip(np.searchsorted(Z,top)-1,0,len(Z)-2)
        fraction=(top-Z[index])/(Z[index+1]-Z[index])
        def upper(a):
            lo=np.take_along_axis(a,index[None],axis=0)[0]
            hi=np.take_along_axis(a,(index+1)[None],axis=0)[0]
            return lo+(hi-lo)*fraction
        du=upper(ambient_u)-ambient_u[0]
        dv=upper(ambient_v)-ambient_v[0]
        return du,dv

    def inflow_shear(self,u,v,nx,ny,head_depth=None):
        du,dv=self.environmental_shear(u,v,head_depth)
        return np.maximum(du*nx+dv*ny,0)

    def cold_head_balance(self,speed,du,dv,nx,ny):
        normal=np.maximum(du*nx+dv*ny,0)
        balance=2*speed*normal/np.maximum(speed**2+normal**2,1)
        if self.astra_updates:
            # A 2-D upright head closure is least representative on strongly
            # oblique flanks: along-boundary shear tilts/segments the plume
            # rather than opposing its cross-line cold-current circulation.
            # Without this coherence factor weak normal projections sustained
            # one huge arc just as readily as the principal downshear head.
            alignment=normal/np.maximum(np.hypot(du,dv),1e-9)
            # Normal shear already reduces the circulation term above.
            # Raising alignment to 2.5 as well starved the weak connections
            # between bows, preventing one coherent regenerating boundary.
            # One additional projection retains flank preference without
            # suppressing all realistically oblique warm-side inflow.
            balance*=alignment
        return balance

    def mature_genesis_line(self,mature):
        """Do not terminate the mother confluence after just one small bow.

        A few mature grid cells met the old area-only test, especially in
        Sol, before neighbouring thermals could join the same boundary. The
        finite meridional confluence needs an established connected span;
        fresh-air/energy restrictions and the finite episode end still apply.
        This diagnoses closure only and never adds activity or cold water.
        """
        from scipy.ndimage import label
        components,count=label(mature,structure=np.ones((3,3)))
        # Extending the initiating footprint must not proportionally extend
        # its rear anchoring after a mature shared boundary is established.
        required=max(2*self.dx,1.5*min(self.synoptic.genesis_half_length,190000))
        for component in range(1,count+1):
            y,_=np.nonzero(components==component)
            if len(y)*self.dx**2>1000e6 and (np.ptp(y)+1)*self.dx>=required:
                return True
        # Segmented rain shafts may already share ONE actual density current.
        # Waiting for a pixel-perfect narrow head bridge keeps the mother
        # confluence alive far behind a travelling line and anchors huge curls.
        # Diagnose its established span using cold-air membership, not radar
        # dilation; sparse isolated bows cannot close the release window.
        pools,_=label((self.cold_depth>100)&(self.cold>.5)&(self.air<.1),structure=np.ones((3,3)))
        for ident in np.unique(pools[mature]):
            if not ident:continue
            y,_=np.nonzero(mature&(pools==ident));span=np.ptp(y)+1
            if (len(y)*self.dx**2>1000e6 and span*self.dx>=required
                    and len(np.unique(y))/span>=.55):return True
        return False

    def gust_activation(self,content,depth,edge,balance,source_height,cin):
        # RKW's nearly upright leading jet retains momentum ABOVE the head.
        # Its pressure-work scale is C^2/2 = g*integral(delta_theta)/theta.
        # Requiring the head itself to touch the LFC killed regenerating lines
        # even when that actual work exceeds the parcel's diagnosed CIN.
        reach=np.exp(-source_height/np.maximum(2*depth,150))
        # Contact/occupied AREA is not a per-parcel velocity reduction.
        # Squaring edge before comparing with CIN suppressed the actual
        # pressure work twice in partially occupied heads and weak bow links.
        # First test one contacted parcel against its real inhibition, then
        # weight the activated fraction by actual contact. A dry numerical
        # tail (edge=0), missing inflow or inadequate work still cannot fire.
        work=G*content/295*reach**2*balance
        barrier=np.maximum(-cin,0)
        if not self.astra_updates:
            work*=edge**2
            return np.clip((work-barrier)/np.maximum(50,.5*work),0,1)
        return np.clip(edge,0,1)*np.clip((work-barrier)/np.maximum(50,.5*work),0,1)

    def debit_plumes(self,cloud_gain,dt,u=None,v=None,air_flux=None,vapor_gain=None,source_inflow=None):
        """Share one donor reservoir safely among all receiving plumes."""
        source=self.mu['start_index']
        # Bound the reservoir around the ACTUAL source, not the ground.
        # A 2.2 km MU source previously had no eligible water at all because
        # every source-layer cell failed the ground's lowest-150 hPa cutoff.
        supply,air_mass=self.plume_reservoir()
        reservoir=np.sum(np.where(supply,self.q*self.mass,0),axis=0)
        requested=np.sum(cloud_gain,axis=0)
        if vapor_gain is not None:requested+=np.sum(vapor_gain,axis=0)
        requests=np.bincount(self.donors.ravel(),weights=requested.ravel(),minlength=self.lon.size).reshape(self.shape)
        # Source replenishment/turnover follows the inflow crossing time, not
        # an arbitrary fixed 8%/90 s cap that throttled organized heavy rain.
        if u is None or v is None:u,v=self.winds()
        inflow=np.hypot(np.take_along_axis(u,source[None],axis=0)[0],np.take_along_axis(v,source[None],axis=0)[0])
        if self.astra_updates and source_inflow is not None:
            relative=np.zeros(self.lon.size)
            np.maximum.at(relative,self.donors.ravel(),np.maximum(source_inflow,0).ravel())
            inflow=np.maximum(inflow,relative.reshape(self.shape))
        turnover=np.maximum(300,self.dx/np.maximum(inflow,4))
        if self.astra_updates and air_flux is not None:
            # This plume already asks for a FINITE air mass rho*w*A*dt.
            # A second horizontal turnover fraction rejected most of that
            # physically available condensate even when both source air and
            # moisture remained. Limit shared requests by actual donor air
            # AND water, not another empirical 300-s moisture throttle.
            air_requests=np.bincount(self.donors.ravel(),weights=np.maximum(air_flux,0).ravel(),minlength=self.lon.size).reshape(self.shape)
            factor=np.minimum(1,np.minimum(reservoir/np.maximum(requests,1e-12),air_mass/np.maximum(air_requests,1e-12)))
        else:
            accessible=-np.expm1(-dt/turnover)*reservoir
            factor=np.minimum(1,accessible/np.maximum(requests,1e-12))
        cloud_gain=cloud_gain*self.donor_field(factor)[None]
        if vapor_gain is not None:vapor_gain=vapor_gain*self.donor_field(factor)[None]
        withdrawn=requests*factor
        self.q-=np.where(supply,self.q*withdrawn[None]/np.maximum(reservoir[None],1e-12),0)
        if air_flux is not None:
            accepted=np.where(requested>1e-12,air_flux*self.donor_field(factor),0)
            # Source moisture is already debited above. Record the remaining
            # subgrid stabilization in the actual RECEIVING column; recording
            # it upstream double-penalized fresh inflow before it reached the
            # gust front and left the precipitating wake free to switch layers.
            energy=self.plume_cape(self.donor_field(self.mu['cape']))
            capacity=self.cape_capacity if self.astra_updates else self.cape_ceiling
            used=np.minimum(np.maximum(capacity-self.cape_deficit,0),energy*(-np.expm1(-accepted/np.maximum(air_mass,1))))
            self.cape_deficit+=used;self.cape_consumed+=float(used.sum())
        return cloud_gain if vapor_gain is None else (cloud_gain,vapor_gain)

    def evaporate_rain(self,dt):
        """Ambient rain and moist plume cores do not have equal exposure.

        A core's finite width slows lateral dilution; no synthetic humidity
        or water is supplied. Both losses share the real saturation capacity.
        """
        qs=saturation(self.temp,self.p);dry=np.clip(1-self.q/np.maximum(qs,1e-9),0,1)
        capacity=np.maximum(qs-self.q,0)/(1+LV*LV*qs/(CP*461.5*self.temp**2))
        occupied=np.clip(self.rain_area/np.maximum(self.plume_rain,1e-15),.01,1)
        # Shielding belongs INSIDE a moist cloud core. Below its actual LCL,
        # falling rain meets ambient air and must still supply evaporatively
        # cooled downdrafts; protecting that whole layer erased deep cold pools.
        in_cloud=self.p<=self.donor_field(self.mu['lcl_pressure'])[None]
        if self.astra_updates:
            density=self.mass/DZ[:,None,None]
            rate=rain_evaporation_rate(self.plume_rain,density,self.temp,self.p,occupied)
            mixing_time=1/np.maximum(rate,1e-12)+in_cloud*self.dx*np.sqrt(occupied)/8
        else:mixing_time=180+in_cloud*self.dx*np.sqrt(occupied)/8
        core_loss=self.plume_rain*dry*(-np.expm1(-dt/mixing_time))
        if self.astra_updates:
            # A narrow rain shaft cannot use the saturation deficit of the
            # entire grid cell. That over-evaporated cores, diluted rainfall
            # and produced implausibly large local downdraft temperatures.
            core_loss=np.minimum(core_loss,capacity*occupied)
        background=np.maximum(self.rain-self.plume_rain,0)
        background_rate=rain_evaporation_rate(background,density,self.temp,self.p) if self.astra_updates else 1/180
        background_loss=background*dry*(-np.expm1(-dt*background_rate))
        demand=core_loss+background_loss
        factor=np.minimum(1,capacity/np.maximum(demand,1e-15))
        core_loss*=factor;evaporation=demand*factor
        self.rain_water_evaporated+=float(np.sum(evaporation*self.mass,dtype='float64'))
        retained=1-core_loss/np.maximum(self.plume_rain,1e-15)
        self.plume_rain-=core_loss;self.rain_area*=retained
        background=np.maximum(self.rain-self.plume_rain-core_loss,0)
        self.stratiform_rain*=1-background_loss*factor/np.maximum(background,1e-15)
        self.rain-=evaporation;self.q+=evaporation;self.temp-=LV/CP*evaporation
        return evaporation

    def plume_coverage(self,support,cell_area,efficiency):
        # Activity is a lifecycle/organization index, NOT a second occupied
        # area or a velocity multiplier. Use one finite fractional area for
        # mass flux, cloud conversion and the rain-area/radar moment alike.
        base=.015 if self.astra_updates else .12
        # New initiation already contains thermodynamic support/entry cost.
        # Do not debit that SAME barrier a second time in occupied area.
        factor=1 if self.astra_updates else support*efficiency
        envelope=np.minimum(.55,(base+.72*self.organization)*cell_area*factor)
        return envelope*np.clip(self.activity,0,1)

    def organized_coverage(self,base,updraft,inflow,depth,activation,support,efficiency,feeding,cell_area=1.,supply_depth=None):
        if not self.astra_updates:return base
        # An established density-current head supplies a finite horizontal
        # air flux H*V/dx. New columns must not each wait through a second
        # arbitrary updraft spin-up while an organized line crosses them.
        # Once a pressure head can lift a real parcel, its overturning inflow
        # includes the diagnosed moist source layer, not just the thin cold
        # volume at the leading numerical edge. Using that tail's H as the
        # whole supply depth throttled strong cores to drizzle-like fluxes.
        capture=depth if supply_depth is None else np.maximum(depth,supply_depth)
        through_head=np.maximum(inflow,0)*np.clip(capture,0,2200)/self.dx
        # Organization diagnoses a coherent boundary, not a second occupied
        # cloud-area fraction. Mature heads may turn the finite incoming air
        # flux upward; weak/unformed heads still spin up continuously.
        coherent=np.clip(self.organization/.2,0,1)*np.minimum(cell_area,1)
        active=through_head*coherent*activation*feeding
        return np.maximum(base,np.minimum(.55,active/np.maximum(updraft,1)))

    def cell_variability(self):
        """Correlated finite cloud clusters, not noise added to radar colours.

        The advected 20-min seed stream modulates plume occupied area once.
        Thus a stronger segment produces/debits more condensate, heavy rain
        and evaporative cold-pool supply; the links remain weaker but real.
        No seed forces a particular bow position, track or storm lifetime.
        """
        sigma=.65*self.cfg['stochastic']
        # This dimensionless unresolved-cluster process must retain its
        # prescribed statistical strength. Passive-scalar interpolation was
        # diffusing it into almost uniform mass flux, making a smooth giant
        # bow. Normalize the stochastic PROCESS, never rain/radar/temperature.
        # Unit mean prevents this correction from raising mean potential
        # coverage; actual shared donor budgets/area limits still apply.
        # Cluster variability belongs to embedded segments, not one broad
        # 100--200 km lobe. Scalar advection preferentially erased the small
        # scales; re-normalizing the remaining broad mode then amplified an
        # entire giant bow. Remove only that stochastic long-wave component.
        # Environmental CAPE/winds and prognostic cold/rain fields are intact.
        anomaly=self.cell_noise-gaussian_filter(self.cell_noise,max(1,34/self.cfg['grid_km']))
        spread=float(anomaly.std())
        if sigma==0 or spread<1e-6:return np.ones(self.shape)
        factor=np.exp(sigma*np.clip(anomaly/spread,-2.5,2.5))
        return factor/float(factor.mean())

    def source_inflow_layer(self,u,v):
        """Mass-weighted REAL donor layer, not a friction-slowed ground wind.

        The same finite moist layer is later debited by debit_plumes. An
        elevated source uses its own layer; no fictitious surface moisture
        or independently chosen extra air reservoir is supplied here.
        """
        supply,mass=self.plume_reservoir()
        weights=np.where(supply,self.mass,0)
        layer_u=np.sum(u*weights,axis=0)/np.maximum(mass,1)
        layer_v=np.sum(v*weights,axis=0)/np.maximum(mass,1)
        density=np.take_along_axis(self.mass/DZ[:,None,None],self.mu['start_index'][None],axis=0)[0]
        depth=mass/np.maximum(density,.1)
        return self.donor_field(layer_u),self.donor_field(layer_v),self.donor_field(depth)

    def head_inflow(self,cell_u,cell_v,cold_u,cold_v,u,v,nx,ny,layer=None):
        if not self.astra_updates:
            su=self.donor_field(np.take_along_axis(u,self.mu['start_index'][None],axis=0)[0])
            sv=self.donor_field(np.take_along_axis(v,self.mu['start_index'][None],axis=0)[0])
            return np.maximum((cell_u-su)*nx+(cell_v-sv)*ny,(cold_u-su)*nx+(cold_v-sv)*ny)
        source_u,source_v,_=self.source_inflow_layer(u,v) if layer is None else layer
        # Use an actual storm/material reference frame. Adding sqrt(g Q)
        # AGAIN to an already accelerated outflow manufactured fresh inflow
        # around the whole huge arc, including receding flanks.
        cells=(cell_u-source_u)*nx+(cell_v-source_v)*ny
        current=(cold_u-source_u)*nx+(cold_v-source_v)*ny
        # Expansion of the pool alone is NOT an independent warm inflow.
        # In particular, the northern flank of an eastward system may be
        # overtaken by the southerly source-layer jet. It cannot keep making
        # new deep plumes merely because cold material also spreads north.
        return np.where(cells>1e-6,np.maximum(cells,current),0)

    def downdraft_momentum(self,evaporation,dt):
        """Precipitation/evaporation work and conservative downward mixing.

        `downburst_energy` is a diagnostic parcel-work reservoir (J/kg), not
        an extra water/heat source. Horizontal momentum is exchanged with
        the actual 0.35--4.5 km precipitation-bearing layers, not multiplied.
        """
        self.downdraft_mass_depth.fill(0)
        if not self.astra_updates:return
        if not np.any(evaporation[2:9]) and not np.any(self.rain[2:9]):return
        density=self.mass/DZ[:,None,None]
        core_cover=np.clip(self.rain_area/np.maximum(self.plume_rain,1e-15),.03,1)
        # Background rain occupies the full cell; do not concentrate its work
        # into an unrelated tiny convective core in the same column.
        core_share=np.clip(self.plume_rain/np.maximum(self.rain,1e-15),0,1)
        cover=core_share*core_cover+(1-core_share)
        cooling=np.maximum(evaporation*(LV/CP-.61*self.temp),0)
        source=(Z[:,None,None]>=350)&(Z[:,None,None]<=4500)
        fall=rain_fall_speed(self.rain,density,cover)
        evaporative=G*cooling*DZ[:,None,None]/np.maximum(self.temp,200)
        loading=G*self.rain*np.minimum(fall*dt,DZ[:,None,None])
        work=(evaporative+loading)*source
        before_t=self.temp+LV/CP*evaporation;before_q=np.maximum(self.q-evaporation,0)
        qs=saturation(before_t,self.p)
        wetbulb_deficit=np.maximum(qs-before_q,0)/(1+LV*LV*qs/(CP*461.5*before_t**2))
        virtual_deficit=wetbulb_deficit*(LV/CP-.61*before_t)
        # Each arriving parcel has finite wet-bulb/DCAPE-like potential and
        # hydrometeor loading; repeated arrivals are not one parcel cooling
        # without limit. The full model cold-pool pressure budget is separate.
        potential=G*(virtual_deficit/np.maximum(before_t,200)+self.rain/cover)*DZ[:,None,None]
        # Stable subcloud air can arrest descending parcels. This is a bulk
        # wet-potential-temperature barrier, not a full moist DCAPE solver.
        wet_t=before_t-wetbulb_deficit
        wet_q=np.minimum(saturation(wet_t,self.p),before_q+CP/LV*wetbulb_deficit)
        theta_wet=virtual(wet_t,wet_q)*(100000/self.p)**(RD/CP)
        theta_surface=virtual(before_t[0],before_q[0])*(100000/self.p[0])**(RD/CP)
        barrier=.5*G*np.maximum(theta_wet-theta_surface[None],0)*Z[:,None,None]/np.maximum(theta_surface[None],200)
        parcel_work=np.sum(potential*source,axis=0)
        reaches_surface=np.exp(-barrier/np.maximum(parcel_work[None],25))
        # Only an unresolved fraction of parcel work survives entrainment,
        # vertical-to-horizontal conversion and impact mixing. The remaining
        # cooling already supplies the resolved cold pool. Never add sqrt(2E)
        # directly to the background wind as an aligned velocity vector.
        conversion=.30
        self.downburst_energy+=conversion*np.sum(work/cover*reaches_surface,axis=0)
        self.downburst_energy=np.minimum(self.downburst_energy,conversion*np.sum(potential*source*reaches_surface,axis=0))
        weights=(evaporation+ self.rain*np.minimum(fall*dt/DZ[:,None,None],1))*self.mass*source*reaches_surface
        norm=weights.sum(axis=0);shares=weights/np.maximum(norm[None],1e-15)
        self.downburst_area=np.where(norm>0,np.sum(shares*cover,axis=0),self.downburst_area)
        speed=np.sqrt(2*np.maximum(self.downburst_energy,0))
        u,v=self.winds()
        source_density=np.sum(shares*density,axis=0)
        self.downdraft_mass_depth=source_density*speed*self.downburst_area*dt/np.maximum(density[0],.2)*(norm>0)
        exchanged=self.mass[0]*self.downburst_area*(-np.expm1(-source_density*speed*dt/np.maximum(self.mass[0],1)))
        # Each source layer and the receiving lowest layer exchange the same
        # finite air mass. Convex mixing cannot invent horizontal kinetic energy.
        available=np.min(np.where(shares>1e-12,.3*self.mass/np.maximum(shares,1e-15),np.inf),axis=0)
        exchanged=np.minimum(np.minimum(exchanged,.45*self.mass[0]),available)*(norm>0)
        layer_mass=exchanged[None]*shares
        du=layer_mass*(u-self.u[None]);dv=layer_mass*(v-self.v[None])
        delta_u=du.sum(axis=0)/self.mass[0];delta_v=dv.sum(axis=0)/self.mass[0]
        self.u+=delta_u;self.v+=delta_v
        # winds() blends the lowest-level perturbation into the layers above.
        # Cancel that implicit copy before applying the equal/opposite source
        # debit, otherwise a surface acceleration would also create momentum
        # throughout the lower column.
        coupling=np.exp(-(Z-Z[0])/650);coupling[0]=0
        self.momentum_u-=du/self.mass+delta_u[None]*coupling[:,None,None]
        self.momentum_v-=dv/self.mass+delta_v[None]*coupling[:,None,None]

    def transport_downburst(self,dt,u,v,layer_adv):
        if not self.astra_updates:return
        for key in ['momentum_u','momentum_v']:
            a=getattr(self,key)
            if np.any(a):setattr(self,key,layer_adv(a,dt,boundary=0)*math.exp(-dt/10800))
        if np.any(self.downburst_energy):
            # A finite downdraft footprint spreads/mixes on its crossing time;
            # the peak must disappear after the precipitating head has left.
            speed=np.sqrt(2*np.maximum(self.downburst_energy,0))
            tau=np.clip(self.dx*np.sqrt(self.downburst_area)/np.maximum(speed,5),120,600)
            energy=advect(self.downburst_energy,u[0],v[0],dt,self.dx,boundary=0)
            speed=np.hypot(self.u,self.v)
            stress=1+self.drag_coefficient(speed)*speed*dt/DZ[0]
            self.downburst_energy=np.maximum(energy,0)*np.exp(-dt/tau)/stress**2

    def surface_gust(self):
        mean=np.hypot(self.u,self.v)
        if not self.astra_updates:return mean
        # Peak parcel impact is separate from grid-mean wind. No additive
        # cold-pool pressure work: that already drives the resolved outflow.
        ambient=np.hypot(self.syn_u,self.syn_v)
        resolved=.5*np.maximum(mean**2-ambient**2,0)
        unresolved=np.maximum(self.downburst_energy-resolved,0)
        # Ordinary turbulent gusts exist even without a downburst. Friction
        # velocity supplies the shear-generated variance; bulk stability
        # reduces mixing over a stable surface. Keep convective energy in
        # quadrature, not an aligned addition of ideal DCAPE/free-fall speed.
        theta=virtual(self.temp[:2],self.q[:2])*(100000/self.p[:2])**(RD/CP)
        ri=G*(theta[1]-theta[0])*(Z[1]-Z[0])/(np.maximum(theta[0],200)*(mean**2+4))
        mixing=1/np.sqrt(1+5*np.maximum(ri,0))
        turbulent=3*np.sqrt(self.drag_coefficient(mean))*mean*mixing
        # Explicit scenario envelope requested for StormSim: never manufacture
        # a 32-m/s gust, but do not publish unrealistically unbounded peaks.
        return np.minimum(32.,np.sqrt((mean+turbulent)**2+2*unresolved))

    def organization_timescale(self,depth,speed,balance):
        # A mature head turns inflow upward in H/(C*balance), not a fixed
        # 15 minutes at EACH newly reached cell. Three overturning times keep
        # finite spin-up but let a translating, already coherent head persist.
        return np.clip(3*depth/np.maximum(speed*balance,1),120,900)

    def evolve_head_organization(self,dt,target,depth,speed,balance):
        # Updated physics already carried this memory on the density-current
        # flux. Advecting it AGAIN with surface wind stranded coherent lift
        # behind the leading head and restarted every connecting column.
        if not self.astra_updates:
            self.organization=advect(self.organization,self.u,self.v,dt,self.dx,boundary=0)
        tau=np.where(target>self.organization,self.organization_timescale(depth,speed,balance),5400)
        self.organization=np.clip(self.organization+(target-self.organization)*dt/tau,0,1)

    def accrete_cloud(self,dt):
        density=self.mass/DZ[:,None,None]
        occupied=np.clip(self.rain_area/np.maximum(self.plume_rain,1e-15),.01,1)
        liquid=np.clip((self.temp-268.15)/5,0,1)
        core=self.plume_cloud*(-np.expm1(-dt*collection_rate(self.plume_rain,density,occupied)))*liquid
        background=np.maximum(self.cloud-self.plume_cloud,0)*(-np.expm1(-dt*collection_rate(
            np.maximum(self.rain-self.plume_rain,0),density)))*liquid
        if self.astra_updates:self.plume_cloud_area*=1-core/np.maximum(self.plume_cloud,1e-15)
        self.cloud-=core+background;self.plume_cloud-=core
        self.rain+=core+background;self.plume_rain+=core;self.rain_area+=core*occupied

    def frontal_lifting(self,syn_convergence,convergence,uphill,trough_ascent):
        """Stalled-front confluence is shallow; displacement cannot grow forever.

        Estimate normal motion around the actual air=.5 contour. Opposing
        north/south inflows are averaged at that contour, not mistaken for a
        southward-moving front on its cold flank. Stratification restores a
        displaced parcel; genuinely advancing fronts retain deeper forcing.
        """
        ay,ax=np.gradient(self.air,self.dx);gradient=np.hypot(ax,ay)
        normal=-(self.syn_u*ax+self.syn_v*ay)/np.maximum(gradient,1e-12)
        weight=gradient*np.exp(-((self.air-.5)/.13)**2)
        sigma=max(.5,18/self.cfg['grid_km'])
        mean=gaussian_filter(weight*normal,sigma)/np.maximum(gaussian_filter(weight,sigma),1e-12)
        advancing=np.clip(mean/3,0,1)
        self.front_advance=advancing
        frontal=4*self.air*(1-self.air)
        depth=1000*(1-frontal)+frontal*(150+1250*advancing)
        self.ascent_depth=3500*(1-frontal)+frontal*(450+2550*advancing)
        self.w=np.clip(1000*(convergence-syn_convergence)+depth*syn_convergence
                       +uphill*.12+trough_ascent,-.4,.8)
        self.background_w=np.clip(depth*syn_convergence+uphill*.12+trough_ascent,-.4,.8)
        theta=virtual(self.temp,self.q)*(100000/self.p)**(RD/CP)
        n=np.sqrt(np.maximum(G*(theta[4]-theta[1])/(np.maximum(theta[1],200)*(Z[4]-Z[1])),0))
        return 1/7200+frontal*(1-advancing)*n

    def synoptic_adjustment_rate(self):
        """Pressure-flow response must resolve an advancing frontal passage.

        A fixed two-hour relaxation blurred a 30--60-minute confluence
        impulse after lee acceleration. Use the diagnosed 18-km pressure
        transition crossing time, not artificial CAPE or vertical forcing.
        A stationary boundary gets no additional moving-front response.
        """
        _,permission=self.synoptic.genesis(self.time)
        external=self.synoptic.external_air()
        transition=np.maximum(4*self.air*(1-self.air),4*external*(1-external))
        passage=np.maximum(self.synoptic.speed(self.time),0)[None]/18000
        frontal=np.minimum(transition*passage,1/900)
        return 1/7200+permission/1800+frontal

    def outflow_origin(self,u,v):
        """Source geometry for NEW ice; old ice carries its own origin.

        The cloud/inflow shear sets front-to-rear export, not the normal of
        each curved surface-pressure flank. The latter rotated southern ice
        into the along-line flow and stranded its rear weak-echo reservoir.
        Convective lifting still uses the actual local cold-head pressure.
        """
        if self.astra_updates:
            cu,cv=self.storm_motion(u,v)
            cloud_u,cloud_v=self.steering(u,v)
            x=cloud_u-u[4];y=cloud_v-v[4]
            length=np.maximum(np.hypot(x,y),1e-9)
            nx=x/length;ny=y/length
            energy=self.plume_cape(self.donor_field(self.mu['cape']))
            # A finite bulk circulation calibration, not an imposed western
            # echo mask. Only newly detrained CONVECTIVE ice receives it;
            # no available source energy means no added rear circulation.
            # Existing ice retains its transported origin moments and still
            # falls, sublimates, aggregates and melts from its actual water.
            speed=np.minimum(35,np.sqrt(2*np.maximum(energy,0))*.45)
            return nx,ny,cu*nx+cv*ny-speed
        # Retain the historical reference branch for old-model comparisons.
        head=self.cold_head_pressure()
        hy,hx=np.gradient(head,self.dx);gradient=np.hypot(hx,hy)
        edge=np.clip(gradient/np.maximum(self.cold_depth,100)*25000,0,1)
        weight=self.activity*(.2+self.organization)*edge
        scale=max(.5,36/self.cfg['grid_km'])
        norm=gaussian_filter(weight,scale)
        nx=gaussian_filter(-hx/np.maximum(gradient,1e-10)*weight,scale)/np.maximum(norm,1e-9)
        ny=gaussian_filter(-hy/np.maximum(gradient,1e-10)*weight,scale)/np.maximum(norm,1e-9)
        coherence=np.hypot(nx,ny);nx/=np.maximum(coherence,1e-9);ny/=np.maximum(coherence,1e-9)
        cu,cv=self.storm_motion(u,v)
        # A deliberately slower storm PATTERN is not its undamped cloud-layer
        # wind. Subtracting a fast LLJ from the damped pattern could reverse
        # the birth normal and send the first detrained ice AHEAD of the line.
        cloud_u,cloud_v=self.steering(u,v)
        fallback_x=cloud_u-u[4];fallback_y=cloud_v-v[4]
        fallback_norm=np.hypot(fallback_x,fallback_y)
        has_edge=(norm>1e-4)&(coherence>.25)
        nx=np.where(has_edge,nx,fallback_x/np.maximum(fallback_norm,1e-9))
        ny=np.where(has_edge,ny,fallback_y/np.maximum(fallback_norm,1e-9))
        # Storm-relative rearward export was too slow compared with the
        # fall/aggregation time: almost all ice melted under the narrow head.
        # Only new CONVECTIVE ice carries this finite circulation; ambient
        # frontal cloud and old, already-carried source moments stay intact.
        # A regenerating plume uses its actual WARM DONOR, not the exhausted
        # cold column beneath its updraft. Local CAPE often vanishes there;
        # using it shut down rear export precisely in a mature squall line.
        source_energy=self.plume_cape(self.donor_field(self.mu['cape']))
        rear_speed=np.minimum(20,np.sqrt(2*np.maximum(source_energy,0))*.25)
        return nx,ny,cu*nx+cv*ny-rear_speed

    def anvil_winds(self,u,v):
        """Persistent, ice-borne front-to-rear transport; along-line wind stays.

        The source moments survive parent-cell decay and follow advection,
        fallout, deposition and melting. No cold-pool echo mask or track.
        Opposing source normals mix and reduce the diagnosed circulation.
        """
        nx=self.anvil_nx/np.maximum(self.anvil,1e-15)
        ny=self.anvil_ny/np.maximum(self.anvil,1e-15)
        coherence=np.minimum(np.hypot(nx,ny),1.)
        length=np.maximum(np.hypot(nx,ny),1e-9)
        nx=nx/length;ny=ny/length
        target=self.anvil_motion/np.maximum(self.anvil,1e-15)
        correction=np.maximum(u*nx+v*ny-target,0)*coherence
        return u-correction*nx,v-correction*ny

    def ice_fall_speed(self):
        if not self.astra_updates:return np.ones_like(self.anvil)
        density=self.mass/DZ[:,None,None]
        radius=self.ice_radius()
        # Dilution reduces particle NUMBER, not each surviving particle's
        # size. Deposition/aggregation grow the particles and their fall speed.
        return np.clip(1.4*(radius/.00015)**.55*(1.225/np.maximum(density,.15))**.35,.15,4.2).astype(self.anvil.dtype,copy=False)

    def ice_radius(self):
        number=self.anvil_number if hasattr(self,'anvil_number') else np.zeros_like(self.anvil)
        # Infer missing number only for an existing initialized ice reservoir;
        # no crystals and no ice never nucleates cloud from supersaturation.
        fresh_mass=4/3*math.pi*300*.00015**3
        number=np.where(number>0,number,np.maximum(self.anvil,0)/fresh_mass)
        mass_per_particle=np.divide(np.maximum(self.anvil,0),number,out=np.full_like(self.anvil,fresh_mass),where=number>0)
        return np.clip((mass_per_particle/(4/3*math.pi*300))**(1/3),1e-6,.004)

    def limit_ice_number(self):
        # The existing radius closure cannot represent crystals below 1 um.
        # Once sublimating particles reach that size, retire NUMBER in the
        # same proportion instead of leaving finite number on vanishing ice.
        # Ice/water/heat are untouched; this is not an echo-mass threshold.
        minimum_mass=4/3*math.pi*300*(1e-6)**3
        self.anvil_number=np.minimum(np.maximum(self.anvil_number,0),np.maximum(self.anvil,0)/minimum_mass)

    def aggregate_ice_number(self,dt):
        density=self.mass/DZ[:,None,None];radius=self.ice_radius()
        # Differential-settling collisions decrease crystal number while
        # conserving ice mass. A bulk width / collection efficiency, not an
        # age-based echo fade or a universal measured particle distribution.
        # Sticking is efficient near the dendritic growth zone, not uniformly
        # in the very cold upper anvil. Constant efficiency rapidly converted
        # its entire small-crystal population into fast-falling near-head snow.
        sticking=.3*np.exp(-((self.temp-258.15)/12)**2)
        kernel=4*math.pi*radius**2*(.3*self.ice_fall_speed())*sticking
        self.anvil_number/=1+.5*dt*kernel*density*self.anvil_number

    def graupel_fall_speed(self):
        density=self.mass/DZ[:,None,None]
        area=np.clip(self.graupel_area/np.maximum(self.graupel,1e-15),.01,1)
        content=np.maximum(self.graupel*density/area,0)
        return np.clip((2+3*(content/(content+5e-4))**.25)*
            (1.225/np.maximum(density,.15))**.3,2,8).astype(self.graupel.dtype,copy=False)

    def convective_ice(self,dt,detrain,plume_share):
        """Separate dense precipitating ice from slow detrained cloud ice.

        A mixed-phase/liquid-loading bulk partition, not a rain multiplier.
        The same condensate leaves cloud once, keeps its carried core area,
        falls in environmental winds, and becomes core rain only on melting.
        """
        density=self.mass/DZ[:,None,None]
        cover=np.clip(self.plume_cloud_area/np.maximum(self.plume_cloud,1e-15),.01,1)
        loading=self.plume_cloud*density/cover
        mixed=np.exp(-((self.temp-263.15)/14)**2)
        rime_fraction=mixed*loading/(loading+5e-4)
        # Cold dense cores also grow precipitating aggregates: limiting the
        # fast reservoir to liquid riming parked most deep-plume condensate
        # in slow cloud ice, delaying rain into a huge, weak trailing shield.
        # Unrimed ice must first enter the transported ice/NUMBER reservoir.
        # The old instantaneous aggregation split put most fresh upper ice
        # straight into fast graupel, bypassing crystal number evolution for
        # that fraction before any rearward transport. Unrimed ice now uses
        # the explicit number/aggregation/fallout pathway after detrainment.
        precipitating=rime_fraction
        rimed=detrain*plume_share*precipitating
        self.graupel+=rimed;self.graupel_area+=rimed*cover
        self.plume_cloud_area*=1-detrain*plume_share/np.maximum(self.plume_cloud,1e-15)
        return rimed

    def collect_precipitating_ice(self,dt):
        """Finite frozen-particle sweepout of existing water, not rain scaling.

        Dense precipitating ice was only born once and never collected cloud
        afterwards, so too much of a core escaped into slow trailing ice.
        A bulk particle radius/density closes the geometrical collection area.
        """
        if not self.astra_updates or not np.any(self.graupel):return
        density=self.mass/DZ[:,None,None]
        cover=np.clip(self.graupel_area/np.maximum(self.graupel,1e-15),.01,1)
        content=self.graupel*density/cover
        radius=np.clip(.0006*(np.maximum(content,1e-12)/.0005)**.2,.0003,.0015)
        sweep=3*.6*self.graupel_fall_speed()*content/(4*400*radius)
        fraction=-np.expm1(-dt*sweep)*(self.temp<273.15)
        # Convective liquid is colocated with its core; environmental cloud
        # and detrained anvil fill only the actually intercepted area.
        cloud_area=np.clip(self.plume_cloud_area/np.maximum(self.plume_cloud,1e-15),.01,1)
        overlap=np.minimum(cover,cloud_area)/cloud_area
        plume=self.plume_cloud*fraction*overlap
        ambient=np.maximum(self.cloud-self.plume_cloud,0)*fraction*cover
        ice=self.anvil*fraction*cover
        retained=np.divide(self.anvil-ice,self.anvil,out=np.zeros_like(self.anvil),where=self.anvil>0)
        for key in ['anvil_nx','anvil_ny','anvil_motion','anvil_convective','anvil_number']:setattr(self,key,(getattr(self,key)*retained).astype(self.anvil.dtype,copy=False))
        self.anvil-=ice
        self.plume_cloud_area*=1-plume/np.maximum(self.plume_cloud,1e-15)
        self.plume_cloud-=plume;self.cloud-=plume+ambient
        gained=plume+ambient+ice;self.graupel+=gained;self.graupel_area+=gained*cover
        self.temp+=LF/CP*(plume+ambient)

    def sediment_convective_ice(self,dt):
        if not self.astra_updates or not np.any(self.graupel):return np.zeros(self.shape)
        qs=saturation_ice(self.temp,self.p)
        capacity=np.maximum(qs-self.q,0)/(1+(LV+LF)**2*qs/(CP*461.5*self.temp**2))
        dry=np.clip(1-self.q/np.maximum(qs,1e-12),0,1)
        loss=np.minimum(capacity,self.graupel*(-np.expm1(-dt*dry/900)))*(self.temp<273.15)
        self.graupel_area*=1-loss/np.maximum(self.graupel,1e-15)
        self.graupel-=loss;self.q+=loss;self.temp-=(LV+LF)/CP*loss
        speed=self.graupel_fall_speed()
        self.graupel,fallen=sediment(self.graupel,self.mass,dt,speed)
        self.graupel_area,_=sediment(self.graupel_area,self.mass,dt,speed)
        melted=self.graupel*np.minimum(1,dt/120*np.maximum(self.temp-273.15,0)/4)
        area=melted*self.graupel_area/np.maximum(self.graupel,1e-15)
        self.graupel-=melted;self.graupel_area-=area
        self.rain+=melted;self.plume_rain+=melted;self.rain_area+=area
        self.temp-=LF/CP*melted
        return fallen

    def mix_stratiform_air(self,dt):
        """Closed pairwise vapour/heat mixing at cloudy-air interfaces.

        Detached, nearly saturated grid boxes must be able to entrain their
        neighbouring dry air. No prescribed environmental humidity reservoir
        or cold-pool/distance echo mask supplies/removes water.
        """
        if not self.astra_updates or not np.any(self.anvil>1e-8):return
        presence=np.clip(self.anvil/1e-4,0,1)
        theta=self.temp*(100000/self.p)**(RD/CP)
        for axis,coefficient in [(-1,2000.),(-2,2000.),(0,12.)]:
            a=[slice(None)]*3;b=a.copy();a[axis]=slice(None,-1);b[axis]=slice(1,None)
            a=tuple(a);b=tuple(b)
            distance=np.diff(Z)[:,None,None] if axis==0 else self.dx
            fraction=np.minimum(.1,coefficient*dt/distance**2)*np.maximum(presence[a],presence[b])
            exchange=fraction*np.minimum(self.mass[a],self.mass[b])
            water=exchange*(self.q[a]-self.q[b]);heat=exchange*(theta[a]-theta[b])
            self.q[a]-=water/self.mass[a];self.q[b]+=water/self.mass[b]
            theta[a]-=heat/self.mass[a];theta[b]+=heat/self.mass[b]
        self.temp=(theta*(self.p/100000)**(RD/CP)).astype('float32')

    def trailing_microphysics(self,dt):
        """Phase-aware bulk ice, vapour growth, rear transport and melting.

        Freezing competes with LIQUID conversion, not a 240 s all-temperature
        rain sink. Existing ice can grow only from actual ice-supersaturated
        vapour. Bulk ice mass and number are carried consistently; this is
        still not a full snow/graupel size-distribution microphysics scheme.
        """
        self.mix_stratiform_air(dt)
        if not hasattr(self,'anvil_number'):self.anvil_number=np.zeros_like(self.anvil)
        if self.astra_updates:self.limit_ice_number()
        fresh_mass=4/3*math.pi*300*.00015**3
        self.anvil_number=np.where((self.anvil>0)&(self.anvil_number<=0),self.anvil/fresh_mass,self.anvil_number).astype(self.anvil.dtype,copy=False)
        frozen=np.clip((273.15-self.temp)/5,0,1)
        detrain=self.cloud*(-np.expm1(-dt*frozen/120))
        plume_fraction=np.minimum(1,self.plume_cloud/np.maximum(self.cloud,1e-15))
        plume_detrain=detrain*plume_fraction
        precipitating=self.convective_ice(dt,detrain,plume_fraction) if self.astra_updates else 0.
        self.plume_cloud-=detrain*plume_fraction;self.cloud-=detrain
        self.temp+=LF/CP*detrain
        detrain-=precipitating
        u,v=self.winds();nx,ny,motion=self.outflow_origin(u,v)
        self.anvil+=detrain
        self.anvil_number+=detrain/fresh_mass
        # Only convective detrainment carries a front-to-rear circulation.
        # Freezing frontal/environmental cloud must stay in the actual wind;
        # tagging all cloud gave stationary frontal rain an artificial wake.
        source_fraction=np.maximum(plume_detrain-precipitating,0)/np.maximum(detrain,1e-15) if self.astra_updates else 1.
        convective=detrain*source_fraction
        self.anvil_convective+=convective
        self.convective_ice_source+=float(np.sum(convective*self.mass))
        self.environmental_ice_source+=float(np.sum((detrain-convective)*self.mass))
        self.anvil_nx+=detrain*source_fraction*nx[None];self.anvil_ny+=detrain*source_fraction*ny[None]
        self.anvil_motion+=detrain*source_fraction*motion[None]
        self.collect_precipitating_ice(dt)
        qs=saturation_ice(self.temp,self.p)
        capacity=(self.q-qs)/(1+(LV+LF)**2*qs/(CP*461.5*self.temp**2))
        # Diffusional growth uses actual crystal number and radius. The old
        # maximum 2-hour deposition time gave any numerical ice wisp a finite
        # whole-cell growth source, repeatedly rebuilding the trailing shield.
        density=self.mass/DZ[:,None,None];radius=self.ice_radius()
        diffusivity=2.2e-5*(self.temp/273.15)**1.94*(101325/self.p)
        resistance=1+(LV+LF)*diffusivity*density*qs/(.022*self.temp)*((LV+LF)/(461.5*self.temp)-1)
        deposition=4*math.pi*radius*diffusivity*density*self.anvil_number/np.maximum(resistance,1)
        if not self.astra_updates:deposition=1/np.clip(600*np.sqrt(1e-4/np.maximum(self.anvil,1e-15)),120,7200)
        growth=np.maximum(capacity,0)*(-np.expm1(-dt*deposition))*(self.anvil>0)*(self.temp<273.15)
        dry=np.clip(1-self.q/np.maximum(qs,1e-12),0,1)
        ventilation=np.sqrt(self.ice_fall_speed()) if self.astra_updates else 1.
        loss=np.minimum(np.maximum(-capacity,0),self.anvil*(-np.expm1(-dt*dry*ventilation/1800)))
        change=growth-loss
        retained=np.divide(self.anvil+change,self.anvil,out=np.zeros_like(self.anvil),where=self.anvil>0)
        for key in ['anvil_nx','anvil_ny','anvil_motion','anvil_convective']:setattr(self,key,(getattr(self,key)*retained).astype(self.anvil.dtype,copy=False))
        self.anvil+=change;self.q-=change;self.temp+=(LV+LF)/CP*change
        self.anvil_number=np.where(self.anvil>0,self.anvil_number,0).astype(self.anvil.dtype,copy=False)
        if self.astra_updates:
            self.limit_ice_number();self.aggregate_ice_number(dt)
        # Identical conservative fall flux for water and its signed moments.
        speed=self.ice_fall_speed()
        for key in ['anvil_nx','anvil_ny','anvil_motion','anvil_convective','anvil_number']:
            updated,_=sediment(getattr(self,key),self.mass,dt,speed=speed)
            setattr(self,key,updated)
        self.anvil,fallen=sediment(self.anvil,self.mass,dt,speed=speed)
        melted=self.anvil*np.minimum(1,dt/180*np.maximum(self.temp-273.15,0)/4)
        retained=np.divide(self.anvil-melted,self.anvil,out=np.zeros_like(self.anvil),where=self.anvil>0)
        for key in ['anvil_nx','anvil_ny','anvil_motion','anvil_convective','anvil_number']:setattr(self,key,(getattr(self,key)*retained).astype(self.anvil.dtype,copy=False))
        self.anvil-=melted;self.rain+=melted;self.stratiform_rain+=melted
        if self.astra_updates:self.limit_ice_number()
        self.temp-=LF/CP*melted
        return fallen+self.sediment_convective_ice(dt)

    def hourly_rain(self):
        """Actual rolling 60-minute accumulation, not instantaneous rate × 1 h."""
        target=max(0,self.time-3600)
        before=self.rain_history[0][1]
        for (ta,a),(tb,b) in zip(self.rain_history,self.rain_history[1:]):
            if ta<=target<=tb:
                before=a+(b-a)*(target-ta)/max(tb-ta,1e-9);break
        return np.maximum(self.total-before,0)

    def step(self, until=None):
        if self.astra_updates:self.limit_ice_number()
        if self.astra_updates and int(self.time//86400)>self.convective_day:
            self.convective_day=int(self.time//86400)
            self.diagnostics()
            self.next_genesis_check=min(self.next_genesis_check,self.time)
        if self.astra_updates and self.time>=self.next_genesis_check:
            self.reconsider_genesis()
        c=self.cfg;u,v=self.winds()
        upstream_temp,upstream_q=self.upstream_environment()
        au,av=self.anvil_winds(u,v) if np.any(self.anvil) else (u,v)
        fastest=max(1,float(np.max(np.abs(u)+np.abs(v))),float(np.max(np.abs(au)+np.abs(av))),float(np.max(np.abs(self.syn_u)+np.abs(self.syn_v))))
        dt=min(90.,.45*self.dx/fastest)
        # Hit physical forcing events exactly. Display/snapshot intervals must
        # not change when a seeded perturbation is drawn or a parcel refreshed.
        for event in [self.next_noise,self.next_cell_noise,self.next_day_noise,self.next_diagnostic,self.next_rain_history,
                      *([self.next_genesis_check] if self.astra_updates else [])]:
            if event>self.time+1e-6:dt=min(dt,event-self.time)
        if until is not None: dt=min(dt,until-self.time)
        if dt<=1e-8:return
        self.max_cfl=max(self.max_cfl,dt/self.dx*fastest)
        if self.time>=self.next_noise:
            alpha=math.exp(-900/3600)
            self.noise=alpha*self.noise+math.sqrt(1-alpha*alpha)*correlated(self.rngs[2],self.shape,max(3,40/c['grid_km']))
            self.next_noise=self.time+900
        if self.time>=self.next_cell_noise:
            alpha=math.exp(-300/1200)
            self.cell_noise=alpha*self.cell_noise+math.sqrt(1-alpha*alpha)*correlated(self.rngs[4],self.shape,max(1,14/c['grid_km']))
            self.next_cell_noise=self.time+300
        if self.time>=self.next_day_noise:
            alpha=math.exp(-21600/86400)
            self.day_noise=alpha*self.day_noise+math.sqrt(1-alpha*alpha)*correlated(self.rngs[3],self.shape,max(3,180/c['grid_km']))
            self.next_day_noise=self.time+21600
        # Conserved water mass transport; record open-boundary net water flux.
        water_before=float(np.sum((self.q+self.cloud+self.rain+self.anvil+self.graupel)*self.mass,dtype='float64' if c['compact_transport'] else None))
        layer_adv=Advection(u,v,self.dx)
        dry_advected=layer_adv(self.mass,dt,conservative=True)
        water_keys=['q','cloud','rain','plume_cloud','plume_rain','rain_area','stratiform_rain']
        if self.astra_updates:water_keys+=['plume_cloud_area','graupel','graupel_area']
        for key in water_keys:
            extensive=getattr(self,key)*self.mass
            upstream=upstream_q*self.mass if key=='q' else 0
            if c['compact_transport']:upstream=np.asarray(upstream,dtype=extensive.dtype)
            updated=layer_adv(extensive,dt,boundary=upstream,conservative=True)
            # Reference-density column closure compensates unresolved vertical
            # mass convergence. Transport a mixing ratio, not compress water
            # indefinitely against a fixed air mass. Included in flux audit.
            updated+=getattr(self,key)*(self.mass-dry_advected)
            if key in ['q','cloud','rain','graupel']:self.numerical_water+=float(np.sum(np.maximum(-updated,0)))
            setattr(self,key,np.maximum(updated,0)/self.mass)
        self.plume_cloud=np.minimum(self.plume_cloud,self.cloud)
        if self.astra_updates:
            self.plume_cloud_area=np.minimum(self.plume_cloud_area,self.plume_cloud)
            self.graupel_area=np.minimum(self.graupel_area,self.graupel)
        self.plume_rain=np.minimum(self.plume_rain,self.rain)
        self.rain_area=np.minimum(self.rain_area,self.plume_rain)
        self.stratiform_rain=np.minimum(self.stratiform_rain,np.maximum(self.rain-self.plume_rain,0))
        if np.any(self.anvil):
            if c['compact_transport']:au,av=au.astype('float32'),av.astype('float32')
            anvil_adv=Advection(au,av,self.dx)
            density_closure=self.mass-anvil_adv(self.mass,dt,conservative=True)
            moment_keys=['anvil_nx','anvil_ny','anvil_motion','anvil_convective','anvil_number']
            old_moments=np.stack([getattr(self,key) for key in moment_keys])
            extensive,moments=anvil_adv.carry(self.anvil*self.mass,old_moments*self.mass[None],dt)
            closure=self.anvil*density_closure
            # Positive reference-air closure supplies the old source mixture;
            # negative closure removes the NEW mixture proportionally. It must
            # not leave source metadata behind after draining its carrier.
            ratio=np.divide(old_moments,self.anvil[None],out=np.zeros_like(old_moments),where=self.anvil[None]>0)
            moments+=ratio*np.maximum(closure,0)[None]
            extensive+=np.maximum(closure,0)
            retained=np.maximum(0,1+np.divide(np.minimum(closure,0),extensive,out=np.zeros_like(extensive),where=extensive>0))
            moments*=retained[None]
            extensive+=np.minimum(closure,0)
            self.numerical_water+=float(np.sum(np.maximum(-extensive,0)))
            self.anvil=np.maximum(extensive,0)/self.mass
            for index,key in enumerate(moment_keys):setattr(self,key,(moments[index]/self.mass).astype(self.anvil.dtype,copy=False))
        water_after=float(np.sum((self.q+self.cloud+self.rain+self.anvil+self.graupel)*self.mass,dtype='float64' if c['compact_transport'] else None))
        self.external_water+=water_after-water_before
        # Non-conservative scalar advection for temperature, with divergence
        # correction. Reference pressure/density make this a reduced model.
        # Use exactly the SAME face divergence as the transport operator.
        # A separate one-sided gradient at open boundaries doubles the source.
        # Middle/upper winds run above terrain, not along every AGL slope.
        # Converting the ENTIRE horizontal flux to fixed-AGL theta without a
        # 3-D coordinate-remapping term created domain-wide artificial foehn
        # warming. Keep reduced-model heat advection; diagnose only finite
        # low-layer terrain ascent/descent below, not a whole-column descent.
        self.temp=layer_adv(self.temp,dt,boundary=upstream_temp)
        self.transport_downburst(dt,u,v,layer_adv)
        old_front_layers=self.frontal_layers() if self.astra_updates else None
        self.air=np.clip(advect(self.air,self.syn_u,self.syn_v,dt,self.dx,
                             boundary=self.synoptic.external_air() if self.astra_updates else None),0,1)
        if self.astra_updates:self.transport_front_thermodynamics(old_front_layers,self.frontal_layers(),layer_adv,dt)
        self.transport_cold_pool(dt)
        self.transport_cape_budget(dt,u,v)
        # Surface sensible/latent exchange and nighttime longwave cooling.
        sun=daylight(self.time)
        optical=np.sum((self.cloud+.6*self.anvil)*self.mass,axis=0)
        solar=sun*np.exp(-optical/.25)
        surface_heat,exchange,target=self.surface_exchange(dt,solar,sun)
        self.recover_cold_pool(dt,surface_heat+.61*self.temp[0]*exchange,solar)
        self.temp[0]+=self.noise*c['stochastic']*.08*dt/3600
        self.temp,self.q=mix_boundary_layer(self.temp,self.q,self.p,self.mass,u,v,dt,solar,self.land_cover)
        self.recover_cape_budget(surface_heat*self.mass[0],exchange*self.mass[0],self.surface_cape_connection(u,v))
        # The Bay trough stays west of the domain; only the independent
        # northern disturbance travels with its own phase speed.
        phase_speed=self.synoptic.phase_speed if self.astra_updates else 1.
        if not self.astra_updates:
            self.trough_lon+=float(np.mean(u[8]))*phase_speed*dt/(111195*math.cos(math.radians(24)))
        self.north_trough_lon+=float(np.mean(u[9]))*self.north_phase_speed*dt/(111195*math.cos(math.radians(25)))
        cooling=np.exp(-((self.lon-self.trough_lon)/1.5)**2)*self.trough_strength
        if self.astra_updates:
            wx,wy,we,ws=self.synoptic.wave(self.time,self.trough_lon)
            # Weak, broad downstream thermal forcing, not a travelling local
            # shortwave or a narrow longitude ribbon.
            cooling=.2*ws*wx*we
        self.temp-=cooling[None]*np.exp(-((Z[:,None,None]-5000)/1800)**2)*dt*.000035
        # Prognostic low-level wind: background pressure forcing, Coriolis,
        # density-current pressure gradient and terrain drag. Not 3D momentum.
        surge=self.synoptic_surge()
        ug=4*(1-self.air)+self.air
        vg=5*c['jet']*(1-self.air)-(5*c['jet']+.5+4*surge)*self.air
        vg-=self.frontal_drift()
        if self.astra_updates:ug,vg=self.synoptic.surface_target(self.air,self.time)
        # Filter pressure at a fixed physical scale: a grid-scale DEM notch
        # must not become an explosive, alternating density-current source.
        # The frontal cold reservoir has its OWN hydrostatic density head.
        # Previously it was only a passive colour tracer: opposing prescribed
        # winds could pin it forever even after the northern surge arrived.
        # The initial broad frontal thermal gradient is part of the balanced
        # background. Only the additional surge head accelerates the front;
        # adding an unbalanced initial head swept it to the sea on day one.
        frontal_head=gaussian_filter(3*self.air*650*surge/295,max(.5,8/c['grid_km'])) if not self.astra_updates else np.zeros(self.shape)
        f=2*7.2921e-5*np.sin(np.radians(self.lat))
        smooth_h=gaussian_filter(self.h,max(.5,12/c['grid_km']))
        su,sv=self.syn_u.copy(),self.syn_v.copy()
        syn_adv=Advection(su,sv,self.dx)
        adjustment=1/7200
        if self.astra_updates:
            # A 25-km mesoscale confluence adjusts faster than the regional
            # reservoir. Two successive 2-h relaxations previously filtered
            # the finite impulse away before parcels could approach the LFC.
            adjustment=self.synoptic_adjustment_rate()
        self.syn_u=syn_adv(su,dt)+dt*((ug-su)*adjustment+f*(sv-vg)-G*np.gradient(frontal_head,self.dx,axis=-1))
        self.syn_v=syn_adv(sv,dt)+dt*((vg-sv)*adjustment-f*(su-ug)-G*np.gradient(frontal_head,self.dx,axis=-2))
        syn_drag=1+dt/21600*(smooth_h/1500)**2
        self.syn_u=np.clip(self.syn_u/syn_drag,-35,35);self.syn_v=np.clip(self.syn_v/syn_drag,-35,35)
        old_u=self.u.copy();old_v=self.v.copy()
        # Transport momentum across the front; without this term the forcing
        # reset warm-side flow in place instead of letting a surge displace it.
        shallow_adv=Advection(old_u,old_v,self.dx)
        self.u=shallow_adv(old_u,dt)+dt*((self.syn_u-old_u)/7200+f*(old_v-self.syn_v))
        self.v=shallow_adv(old_v,dt)+dt*((self.syn_v-old_v)/7200-f*(old_u-self.syn_u))
        cold_u,cold_v=cold_velocity(self.cold_depth,self.cold_mx,self.cold_my)
        coupling=self.cold_surface_coupling(dt)
        self.u+=coupling*(cold_u-self.u);self.v+=coupling*(cold_v-self.v)
        self.surface_friction(dt*.5)
        convergence=-(np.gradient(self.u,self.dx,axis=-1)+np.gradient(self.v,self.dx,axis=-2))
        syn_convergence=-(np.gradient(self.syn_u,self.dx,axis=-1)+np.gradient(self.syn_v,self.dx,axis=-2))
        uphill=self.u*np.gradient(smooth_h,self.dx,axis=-1)+self.v*np.gradient(smooth_h,self.dx,axis=-2)
        self.temp-=G/CP*uphill[None]*.12*dt*np.exp(-Z[:,None,None]/1500)
        thermal=.22*np.sqrt(np.maximum(target-self.temp[0],0))*solar*self.land_cover
        # Synoptic ascent downstream of the southern trough; coherent forcing
        # evolves with the trough, it is NOT an imposed precipitation stripe.
        trough_ascent=.08*c['trough']*np.exp(-((self.lon-self.trough_lon-.8)/1.0)**2)
        if self.astra_updates:trough_ascent=self.synoptic.ascent(self.time,self.trough_lon)
        # Confluence at a stalled shallow front is not a 3.5 km-deep warm
        # plume. Separate synoptic frontal lifting from gust-front lifting;
        # retain saturation/stratiform rain instead of banning frontal rain.
        restoring=self.frontal_lifting(syn_convergence,convergence,uphill,trough_ascent)
        self.lift=np.maximum(0,advect(self.lift,self.u,self.v,dt,self.dx,boundary=0))
        # Turbulent thermals do not lift the SAME parcel at a fixed grid point
        # for hours. Accumulating them emptied CAPE across the entire warm
        # sector before the organized forcing arrived. Retain only resolved
        # displacement; thermals supply a bounded boundary-layer excursion.
        self.lift=np.clip(self.lift+dt*(self.w-self.lift*restoring),0,4000)
        self.synoptic_lift=np.maximum(0,advect(self.synoptic_lift,self.syn_u,self.syn_v,dt,self.dx,boundary=0))
        self.synoptic_lift=np.clip(self.synoptic_lift+dt*(self.background_w-self.synoptic_lift*restoring),0,4000)
        if self.time>=self.next_diagnostic:self.diagnostics()
        # A moist, unstable parcel must still cross its inhibition barrier.
        # Gust-front lifting is enhanced when the cold-pool circulation and
        # shear NORMAL to the outflow boundary have comparable strengths
        # (RKW-inspired closure, not a resolved vorticity budget).
        # A current's leading numerical tail is thin. Its lifting circulation
        # is set by the pressure head BEHIND that edge, not by tail depth.
        # Using grad(temperature deficit) missed edges of an isothermal pool
        # with variable thickness and stopped regeneration altogether.
        head=self.cold_head_pressure()
        cy,cx=np.gradient(head,self.dx)
        grad=np.hypot(cx,cy);nx=-cx/np.maximum(grad,1e-10);ny=-cy/np.maximum(grad,1e-10)
        if self.astra_updates:
            nx,ny=self.cold_head_normal(head)
            # Share the boundary's DIRECTION between neighbouring shafts,
            # but retain the resolved head's actual pressure slope for its
            # contact/lifting strength. Broadening both quantities erased
            # thin connecting heads while leaving the big cores intact.
            resolved=gaussian_filter(self.cold_content,max(.5,6/c['grid_km']))
            gy,gx=np.gradient(resolved,self.dx)
            grad=np.hypot(gx,gy)
        head_depth=maximum_filter(self.cold_depth,size=3,mode='nearest')
        head_content=maximum_filter(self.cold_content,size=3,mode='nearest')
        # Sign matters: shear aids lifting on the downshear flank, not equally
        # on both sides of every outflow (abs() spuriously made circular rings).
        self.donors,_=self.warm_inflow(nx,ny,self.convective_head_edge(grad,head_depth),np.ones(self.shape))
        shear_u,shear_v=self.environmental_shear(u,v,head_depth)
        density_speed=np.sqrt(2*G*head_content/295)
        balance=self.cold_head_balance(density_speed,shear_u,shear_v,nx,ny)
        edge=self.convective_head_edge(grad,head_depth)
        self.donors,feeding=self.warm_inflow(nx,ny,edge,balance)
        cell_u,cell_v=self.storm_motion(u,v)
        inflow_layer=self.source_inflow_layer(u,v)
        approach=self.head_inflow(cell_u,cell_v,cold_u,cold_v,u,v,nx,ny,layer=inflow_layer)
        if self.astra_updates:
            feeding&=approach>0
            # Only descendants of the existing episode may regenerate. A
            # drizzle-made environmental cold patch elsewhere is not a new
            # permitted parent. This is the single-episode scenario boundary,
            # not a water/CAPE reset or a radar-display mask.
            feeding&=maximum_filter(self.activity,size=5,mode='constant')>.01
            self.donors=np.where(feeding,self.donors,np.arange(self.lon.size).reshape(self.shape))
        # Full mechanical head lifting belongs to the regenerating downshear
        # boundary with real unprocessed supply, not its receding rear edge.
        gust_lift=np.minimum(head_depth,1800)*edge*(.35+1.65*balance)*feeding
        self.gust_lift=gust_lift
        fed_cape=self.donor_field(self.mu['cape']);fed_cin=self.donor_field(self.mu['cin'])
        fed_source=self.donor_field(self.mu['start_index'])
        fed_required=np.maximum(self.donor_field(self.mu_lfc)-Z[fed_source],0)
        cell_adv=Advection(cell_u,cell_v,self.dx)
        self.cell_noise=cell_adv(self.cell_noise,dt)
        self.activity=np.clip(cell_adv(self.activity,dt,boundary=0),0,1)
        self.surface_activity=np.minimum(self.activity,np.maximum(cell_adv(self.surface_activity,dt,boundary=0),0))
        # Stochastic variability perturbs existing ascent; it is NOT an
        # independent 280-m elevator in sinking or undisturbed air.
        fluctuation=self.trigger_perturbation(gust_lift)
        # A warm-side MU donor can still originate well ABOVE the surface.
        # Apply the same finite-depth lifting as for local elevated parcels;
        # otherwise drizzle-fed shallow outflows lift a 1–2 km source with
        # the full surface gust and spuriously spawn southward deep lines.
        fed_height=np.maximum(Z[fed_source]-Z[0],0)
        fed_lift=np.maximum(self.elevated_displacement(fed_height,gust_lift,head_depth)+fluctuation,0)
        efficiency,hazard=self.plume_environment(gust_lift,cell_u,cell_v,u,v)
        fed_activation=np.clip((fed_lift-fed_required)/400,0,1)*feeding*efficiency
        fed_activation*=self.plume_cape(fed_cape)>150
        fed_activation*=np.exp(fed_cin/np.maximum(40+fed_lift*.12,1))
        pressure_activation=self.gust_activation(head_content,head_depth,edge,balance,fed_height,fed_cin)
        pressure_activation*=feeding*efficiency*(self.plume_cape(fed_cape)>150)*np.isfinite(fed_required)
        fed_activation=np.maximum(fed_activation,pressure_activation)
        # Density-current convergence already enters the finite gust head.
        # Accumulating it AGAIN in lift lets wake convergence trigger deep
        # cells for hours after the head has passed, including elevated ones.
        available_lift=np.maximum(self.synoptic_lift+gust_lift+np.minimum(500,thermal*1200)*(1-self.wake_fraction())+fluctuation,0)
        # A surface parcel must actually reach its LFC. The old +300 m
        # allowance released inhibited frontal parcels before they crossed
        # the cap, seeding outflow lines from otherwise stalled confluence.
        activation=np.clip((available_lift-self.lfc)/400,0,1)*(self.available_cape(self.sb['cape'])>100)
        activation*=np.exp(self.sb['cin']/np.maximum(40+available_lift*.12,1))
        # Lift an elevated parcel from its diagnosed source level to ITS LFC,
        # with ITS inhibition. A fixed 1200 m/50% trigger over a tracer mask
        # ignored warm-sector elevated storms and produced them in stable air.
        source_height=Z[self.mu['start_index']]
        displacement=np.maximum(self.mu_lfc-source_height,0)
        elevated_lift=self.elevated_displacement(source_height,gust_lift,head_depth)
        elevated=np.clip((elevated_lift-displacement)/500,0,1)*(self.available_cape(self.mu['cape'])>150)*(self.mu['start_index']>0)
        elevated*=np.exp(self.mu['cin']/np.maximum(40+elevated_lift*.12,1))
        if self.astra_updates:
            # The finite mother-system window gates only WARM-sector origin.
            # An independently advancing material front must not be disabled
            # simply because that earlier window closed hours beforehand.
            _,permission=self.synoptic.genesis(self.time)
            if self.genesis_closed:permission=np.zeros(self.shape)
            permission*=self.fresh_initiation_air()
            if np.any(np.maximum(activation,elevated)*permission>.1):self.genesis_started=True
            allowed=np.maximum(permission,self.frontal_initiation_permission())
            activation*=allowed;elevated*=allowed
            # Organization alone can be a weak, dry outflow. Closing the
            # finite pressure episode then stranded inhibited parcels before
            # a rain-producing, self-regenerating mother system existed.
            mature=feeding&(self.organization>.25)&(self.activity>.1)&(self.last_rate>=5)
            # This measures the narrow regenerating HEAD, not the entire
            # storm's area. Requiring 3000 km2 of head kept the old origin
            # firing after a mature line had already left it behind.
            if self.genesis_started and (self.mature_genesis_line(mature)
                    or self.time>self.synoptic.genesis_start+self.synoptic.genesis_duration):
                self.genesis_closed=True
        target_activity=np.maximum(np.maximum(activation,elevated),fed_activation)
        support=np.minimum(self.deep_support,self.donor_field(self.deep_support))
        target_activity*=support
        connection=np.clip(self.sb['cape']/np.maximum(self.mu['cape'],100),0,1)
        origin=np.where(fed_activation>=np.maximum(activation,elevated),self.donor_field(connection),connection)
        # A plume without renewed lifting survives only a finite cloud-column
        # transit, not a fixed 50-minute low-amplitude mass-flux tail. Faster
        # growing buoyant plumes also do not spend ten minutes producing only
        # diffuse ice before their first heavy rain.
        plume_speed=np.maximum(np.minimum(35,np.sqrt(2*self.plume_cape(fed_cape))*.32),3)
        transit=self.donor_field(self.plume_depth)/plume_speed
        growth=np.clip(transit,120,600);decay=np.clip(2*transit,300,1800)
        lifetime=np.where(target_activity>self.activity,growth,decay) if self.astra_updates else np.where(target_activity>self.activity,600,3000)
        self.activity+=(target_activity-self.activity)*np.minimum(1,dt/lifetime)
        self.surface_activity+=(target_activity*origin-self.surface_activity)*np.minimum(1,dt/lifetime)
        self.activity*=np.exp(-dt*hazard/1200)
        self.activity*=np.exp(-dt*(1-self.deep_support)/1800)
        self.surface_activity=np.minimum(self.activity,np.maximum(self.surface_activity*np.exp(-dt*hazard/1200),0))
        self.initiation=target_activity
        # Organization is a prognostic edge memory, not a storm object or a
        # fixed lifetime. Convergence and balanced outflow expand the fraction
        # occupied by plumes; drying or lost lifting makes it decay again.
        if not self.astra_updates:
            source_u=self.donor_field(np.take_along_axis(u,self.mu['start_index'][None],axis=0)[0])
            source_v=self.donor_field(np.take_along_axis(v,self.mu['start_index'][None],axis=0)[0])
            approach=(cold_u-source_u)*nx+(cold_v-source_v)*ny+np.sqrt(G*head_content/295)
        # The expanding current supplies sustained, line-normal inflow even
        # when a grid's surface convergence estimate momentarily changes sign.
        organized_target=edge*balance*np.clip(approach/8,0,1)*feeding
        if not self.astra_updates:organized_target*=support*efficiency
        self.evolve_head_organization(dt,organized_target,head_depth,density_speed,balance)
        cell_area=self.cell_variability() if self.astra_updates else np.exp(.45*c['stochastic']*np.clip(self.cell_noise,-2.5,2.5))
        self.plume_fraction=self.plume_coverage(support,cell_area,efficiency)
        updraft=np.minimum(35,np.sqrt(2*self.plume_cape(fed_cape))*.32)
        self.plume_fraction=self.organized_coverage(self.plume_fraction,updraft,approach,
            head_depth,target_activity,support,efficiency,feeding,cell_area,supply_depth=inflow_layer[2])
        wprofile=self.resolved_ascent(u,v)
        # Resolved column exchange only. The dedicated plume closure below
        # already withdraws convective moisture from the source reservoir;
        # an additional massflux diffusion here processed it a second time,
        # rapidly exhausting the warm-sector boundary layer.
        for k in range(len(Z)-1):
            # Compensating environmental return flow closes the column mass
            # flux. Moving only donor vapour without returning air accumulates
            # spurious moisture in thin near-surface layers.
            exchanged=np.minimum(np.abs(wprofile[k])*dt*self.mass[k]/DZ[k],
                                 .15*np.minimum(self.mass[k],self.mass[k+1]))
            moved=exchanged*(self.q[k]-self.q[k+1])
            self.q[k]-=moved/self.mass[k];self.q[k+1]+=moved/self.mass[k+1]
        theta=self.temp*(100000/self.p)**(RD/CP)
        below=np.concatenate((theta[:1],theta[:-1]),axis=0)
        above=np.concatenate((theta[1:],theta[-1:]),axis=0)
        dzup=np.r_[Z[1]-Z[0],np.diff(Z)][:,None,None]
        dzdown=np.r_[np.diff(Z),Z[-1]-Z[-2]][:,None,None]
        # Grid-mean subsidence compensates subgrid convective ascent. Applying
        # the updraft's dry cooling to the whole environment spuriously creates
        # CAPE; only resolved lifting advects environmental theta here.
        resolved_w=wprofile
        upward=np.minimum(np.maximum(resolved_w,0)*dt/dzup,.45)
        downward=np.minimum(np.maximum(-resolved_w,0)*dt/dzdown,.45)
        theta+=upward*(below-theta)+downward*(above-theta)
        self.temp=(theta*(self.p/100000)**(RD/CP)).astype('float32')
        # Newtonian upper-level radiative relaxation, explicitly external heat.
        self.temp+=(self.radiative_reference-self.temp)*(dt/86400)*np.clip((Z[:,None,None]-8000)/5000,0,1)
        # Subgrid updraft condensate follows the lifted parcel's saturation
        # mixing ratio. Withdraw the same water from its source-layer reservoir;
        # release latent heat into recipient layers. No rain is created from
        # CAPE alone, and no cloud water is created without a moisture debit.
        source=fed_source
        qsource=self.donor_field(np.take_along_axis(self.q,self.mu['start_index'][None],axis=0)[0])
        parcel_q=np.minimum(qsource[None],saturation(self.donor_field(self.mu['path']),self.p))
        drops=np.maximum(parcel_q[:-1]-parcel_q[1:],0)
        drops*=np.arange(len(Z)-1)[:,None,None]>=source[None]
        source_density=self.donor_field(np.take_along_axis(self.mass/DZ[:,None,None],self.mu['start_index'][None],axis=0)[0])
        air_flux=updraft*self.plume_fraction*source_density*dt
        cloud_gain=drops*air_flux[None]
        # Feed the plume from a ~1 km source-layer reservoir, not the tiny
        # bottom 90 m cell. The old single-cell withdrawal exhausted a plume
        # before it could organize while leaving most boundary-layer water idle.
        # Several gust-front cells can share one donor. Aggregate requests
        # BEFORE limiting, then debit that donor once; budget cannot double-use
        # the same moisture at converging cold-pool boundaries.
        # The plume detrains vapour as well as condensate. Transport only the
        # actual parcel/environment excess from a finite, shared donor budget.
        # Omitting it left every rear cloud in the original dry environment.
        weights=drops*np.exp(-((Z[1:,None,None]-6500)/3500)**2)
        weights/=np.maximum(weights.sum(axis=0),1e-15)
        vapor_gain=.2*air_flux[None]*weights*np.maximum(parcel_q[1:]-self.q[1:],0)
        self.plume_water_requested+=float(np.sum(cloud_gain,dtype='float64'))
        cloud_gain,vapor_gain=self.debit_plumes(cloud_gain,dt,u,v,air_flux,vapor_gain,source_inflow=approach)
        self.plume_water_supplied+=float(np.sum(cloud_gain,dtype='float64'))
        self.cloud[1:]+=cloud_gain/self.mass[1:]
        self.plume_cloud[1:]+=cloud_gain/self.mass[1:]
        if self.astra_updates:self.plume_cloud_area[1:]+=cloud_gain/self.mass[1:]*self.plume_fraction[None]
        self.q[1:]+=vapor_gain/self.mass[1:]
        self.temp[1:]+=LV/CP*cloud_gain/self.mass[1:]
        # Saturation adjustment includes latent heat; iterate rather than clamp
        # moisture without tracking condensate and energy.
        for _ in range(3):
            qs=saturation(self.temp,self.p)
            change=(self.q-qs)/(1+LV*LV*qs/(CP*461.5*self.temp**2))
            # Convective cloud occupies a moist subgrid plume, not the entire
            # dry grid box. Finite entrainment evaporation avoids instantly
            # erasing every condensate pulse before warm rain can form.
            plume_evap=self.plume_cloud*(1-np.exp(-dt/(3*2400)))
            environmental_evap=np.maximum(self.cloud-self.plume_cloud,0)*(1-np.exp(-dt/(3*180)))
            evaporatable=plume_evap+environmental_evap
            change=np.maximum(change,-evaporatable)
            plume_loss=np.maximum(-change,0)*plume_evap/np.maximum(evaporatable,1e-15)
            if self.astra_updates:self.plume_cloud_area*=1-plume_loss/np.maximum(self.plume_cloud,1e-15)
            self.plume_cloud-=plume_loss
            self.q-=change;self.cloud+=change;self.temp+=LV/CP*change
        # Threshold is a LOCAL cloud-water concentration. Applying it to
        # diluted grid-mean plume water prevented rain from almost all plumes.
        # Use the same evolving occupied area as the mass-flux closure.
        frozen_fallen=self.trailing_microphysics(dt)
        liquid=np.clip((self.temp-268.15)/5,0,1)
        cloud_cover=np.clip(self.plume_cloud_area/np.maximum(self.plume_cloud,1e-15),.01,1) if self.astra_updates else self.plume_fraction[None]
        plume_conversion=np.maximum(self.plume_cloud-cloud_cover*.0007,0)*(1-math.exp(-dt/240))*liquid
        conversion=plume_conversion+np.maximum(self.cloud-self.plume_cloud-8e-5,0)*(1-math.exp(-dt/600))*liquid
        if self.astra_updates:self.plume_cloud_area*=1-plume_conversion/np.maximum(self.plume_cloud,1e-15)
        self.plume_cloud-=plume_conversion
        self.cloud-=conversion;self.rain+=conversion
        self.plume_rain+=plume_conversion
        self.rain_area+=plume_conversion*cloud_cover
        # Autoconversion seeds drops; mature rain then COLLECTS cloud liquid.
        # A fixed autoconversion-only timer missed the nonlinear growth of
        # heavy convective rain and retained too much water aloft as cloud.
        self.accrete_cloud(dt)
        # Rain evaporation depends on both available drops and undersaturation.
        # The old deficit-only sink evaporated nearly ALL weak rain at each
        # dry level regardless of droplet supply, shutting down surface rain.
        evaporation=self.evaporate_rain(dt)
        self.downdraft_momentum(evaporation,dt)
        self.supply_cold_pool(evaporation)
        self.surface_friction(dt*.5)
        # Conservative sedimentation through layers, with finite terminal speed.
        density=self.mass/DZ[:,None,None]
        occupied=np.clip(self.rain_area/np.maximum(self.plume_rain,1e-15),.01,1)
        background=np.maximum(self.rain-self.plume_rain,0)
        convective_speed=rain_fall_speed(self.plume_rain,density,occupied)
        background_speed=rain_fall_speed(background,density)
        self.stratiform_rain,stratiform_fallen=sediment(self.stratiform_rain,self.mass,dt,background_speed)
        background,falling=sediment(background,self.mass,dt,background_speed)
        self.plume_rain,convective_fallen=sediment(self.plume_rain,self.mass,dt,convective_speed)
        self.rain_area,area_fallen=sediment(self.rain_area,self.mass,dt,convective_speed)
        self.rain=background+self.plume_rain
        falling+=convective_fallen
        falling+=frozen_fallen
        self.total+=falling;self.last_rate=falling*3600/dt
        self.last_stratiform_rate=stratiform_fallen*3600/dt
        # Convective cores occupy only part of a 4–12 km grid cell. Recover
        # their LOCAL flux from the transported occupied-area moment, exactly
        # as radar averages linear Z rather than diluted plume concentration.
        # Preserve/display grid-mean rain separately; no artificial 20 mm floor.
        fraction=np.clip(area_fallen/np.maximum(convective_fallen,1e-15),.01,1)
        self.last_core_rate=(np.maximum(falling-convective_fallen,0)+convective_fallen/fraction)*3600/dt
        self.surface_rain.advance(self.time+dt,dt,convective_fallen,np.maximum(falling-convective_fallen,0),fraction,
                                  velocity=(cell_u,cell_v),dx=self.dx)
        self.time+=dt;self.steps+=1
        if self.astra_updates:
            self.synoptic.advance(dt,self.time-dt,self.syn_u,self.syn_v)
            if self.genesis_started:
                self.synoptic.advect_genesis(dt,self.time-dt,cell_u,cell_v)
        self.gust_peak=max(self.gust_peak,float(self.surface_gust().max()))
        self.meanwind_peak=max(self.meanwind_peak,float(np.hypot(self.u,self.v).max()))
        if self.time>=self.next_rain_history-1e-6:
            self.rain_history.append((self.time,self.total.copy()));self.next_rain_history+=300
            while len(self.rain_history)>2 and self.rain_history[1][0]<=self.time-3600:self.rain_history.pop(0)
        if not all(np.isfinite(x).all() for x in [self.temp,self.q,self.cloud,self.anvil,self.anvil_nx,self.anvil_ny,self.anvil_motion,self.stratiform_rain,self.plume_cloud,self.rain,self.plume_rain,self.rain_area,self.total,self.u,self.v,self.syn_u,self.syn_v,self.air,self.cold,self.cold_depth,self.cold_content,self.cold_mx,self.cold_my,self.activity,self.surface_activity,self.organization,self.cape_deficit,self.synoptic_lift,self.ground_temp]): raise FloatingPointError('Non-finite atmospheric state')
        if self.astra_updates and not all(np.isfinite(x).all() for x in [self.momentum_u,self.momentum_v,self.downburst_energy,self.graupel,self.graupel_area,self.plume_cloud_area,self.anvil_convective,self.anvil_number,self.cape_capacity]):raise FloatingPointError('Non-finite downdraft/convective-ice state')
        if self.astra_updates and self.anvil_number.min()<-1e-8:raise FloatingPointError('Negative ice crystal number')
        if self.astra_updates and (self.anvil_convective.min()<-1e-10 or np.max(self.anvil_convective-self.anvil)>1e-8):raise FloatingPointError('Invalid convective ice provenance subset')
        if self.astra_updates and (self.graupel.min()<-1e-10 or self.graupel_area.min()<-1e-10 or np.max(self.graupel_area-self.graupel)>1e-8 or self.plume_cloud_area.min()<-1e-10 or np.max(self.plume_cloud_area-self.plume_cloud)>1e-8):raise FloatingPointError('Invalid ice/cloud occupied-area partition')
        if self.q.min()<-1e-10 or self.anvil.min()<-1e-10 or self.plume_cloud.min()<-1e-10 or np.max(self.plume_cloud-self.cloud)>1e-8 or self.plume_rain.min()<-1e-10 or np.max(self.plume_rain-self.rain)>1e-8 or self.rain_area.min()<-1e-10 or np.max(self.rain_area-self.plume_rain)>1e-8:raise FloatingPointError('Invalid water partition; stop rather than conceal it')
        if self.stratiform_rain.min()<-1e-10 or np.max(self.stratiform_rain+self.plume_rain-self.rain)>1e-8:raise FloatingPointError('Stratiform/convective rain subsets exceed total rain')
        if self.temp.min()<150 or self.temp.max()>335: raise FloatingPointError('Temperature outside model validity; stop rather than clip silently')

    def audit_state(self):
        current=float(np.sum((self.q+self.cloud+self.rain+self.anvil+self.graupel)*self.mass,dtype='float64')+np.sum(self.total,dtype='float64')) if self.cfg['compact_transport'] else float(np.sum((self.q+self.cloud+self.rain+self.anvil+self.graupel)*self.mass)+np.sum(self.total))
        expected=self.initial_water+self.external_water
        return {'steps':self.steps,'hours':self.time/3600,'max_cfl':self.max_cfl,
                'water_relative_residual':(current-expected)/max(self.initial_water,1),
                'frontal_airmass_exchange_water':self.frontal_exchange_water,
                'plume_condensate_supplied':self.plume_water_supplied,'plume_condensate_requested':self.plume_water_requested,
                'rainwater_evaporated':self.rain_water_evaporated,
                'cold_head_form_drag_dissipation':self.cold_head_dissipation,
                'positivity_correction':self.numerical_water,'temperature_range_K':[float(self.temp.min()),float(self.temp.max())],
                'max_rain_mm_h':float(self.last_rate.max()),'core_rain_max_mm_h':float(self.last_core_rate.max()),'hourly_rain_max_mm':float(self.hourly_rain().max()),'total_rain_max_mm':float(self.total.max()),
                'point_rain5_peak_mm':self.surface_rain.max_five,'point_hour_peak_mm':self.surface_rain.max_hour,'point_total_max_mm':float(self.surface_rain.total.max()),
                'gust_max_m_s':float(self.surface_gust().max()),'gust_peak_m_s':self.gust_peak,'meanwind_peak_m_s':self.meanwind_peak,
                'convective_anvil_mass':float(np.sum(self.anvil_convective*self.mass)),
                'environmental_anvil_mass':float(np.sum(np.maximum(self.anvil-self.anvil_convective,0)*self.mass)),
                'convective_anvil_source':self.convective_ice_source,'environmental_anvil_source':self.environmental_ice_source,
                'max_cape_J_kg':float(self.available_cape(self.mu['cape']).max()),'max_raw_cape_J_kg':float(self.mu['cape'].max()),'active_fraction':float(np.mean(self.activity>.1)),
                'cape_deficit_max_J_kg':float(self.cape_deficit.max()),'cape_consumed_sum':self.cape_consumed,'cape_recovered_sum':self.cape_recovered,
                'coldpool_depth_max_m':float(self.cold_depth.max()),
                'coldpool_max_cfl':self.cold_max_cfl,
                'coldpool_relative_residual':(float(self.cold_content.sum())-self.cold_source-self.cold_external+self.cold_recovery)/max(self.cold_source,1)}

    def fields(self, *, include_mixed=True):
        sb=parcel(self.p,self.temp,self.q,'surface')
        ml=parcel(self.p,self.temp,self.q,'mixed') if include_mixed else None
        mu=parcel(self.p,self.temp,self.q,'unstable');u,v=self.winds()
        def isobaric(a,target):
            out=np.full(self.shape,np.nan,dtype='float32')
            for k in range(len(Z)-1):
                mask=(self.p[k]>=target)&(self.p[k+1]<=target)
                weight=np.log(target/self.p[k])/np.log(self.p[k+1]/self.p[k])
                out=np.where(mask,a[k]*(1-weight)+a[k+1]*weight,out)
            return out
        density=self.mass/DZ[:,None,None]
        background,cores,frozen,occupied=echo_components(self.rain,self.plume_rain,self.rain_area,density,self.anvil,self.graupel,self.graupel_area)
        linear=background+cores+frozen
        dbz=10*np.log10(np.maximum(linear,1e-3))
        environment=np.maximum(self.rain-self.plume_rain,0)
        ambient_fall=rain_fall_speed(environment,density,moment=7)
        core_fall=rain_fall_speed(environment+self.plume_rain/occupied,density,moment=7)
        graupel_z=graupel_echo(self.graupel,self.graupel_area,density)
        anvil_z=np.maximum(frozen-graupel_z,0)
        fall=(background*ambient_fall+cores*core_fall+anvil_z*self.ice_fall_speed()+graupel_z*self.graupel_fall_speed())/np.maximum(linear,1e-12)
        au,av=self.anvil_winds(u,v)
        echo_u=((background+cores+graupel_z)*u+anvil_z*au)/np.maximum(linear,1e-12)
        echo_v=((background+cores+graupel_z)*v+anvil_z*av)/np.maximum(linear,1e-12)
        plume_updraft=np.where(self.activity>0,np.minimum(35,np.sqrt(2*self.plume_cape(self.donor_field(mu['cape']),sb['cape'],mu['cape']))*.32),0)
        return {'temperature':self.temp[0]-273.15,'dewpoint':dewpoint(self.q[0],self.p[0])-273.15,
                'u10':self.u,'v10':self.v,'pressure':self.ps/100,'rainrate':self.last_rate,'rainrate_core':self.last_core_rate,
                **({'gust':self.surface_gust()} if self.astra_updates else {}),
                'rain_total':self.total,'rain_hour':self.hourly_rain(),'sbcape':self.available_cape(sb['cape']),'mucape':self.available_cape(mu['cape']),'mucape_raw':mu['cape'],'cape_deficit':self.cape_deficit,
                **({'mlcape':self.available_cape(ml['cape']),'cin':ml['cin']} if ml is not None else {}),
                'coldpool':self.cold,'coldpool_depth':self.cold_depth,'coldair':self.air,'updraft':plume_updraft,'organization':self.organization,
                'composite':np.max(dbz,axis=0),'u925':isobaric(u,92500),'v925':isobaric(v,92500), 'u500':isobaric(u,50000),'v500':isobaric(v,50000),
                'u300':isobaric(u,30000),'v300':isobaric(v,30000), 'terrain':self.h,
                't3':self.temp-273.15,'q3':self.q,'u3':u,'v3':v,'dbz3':dbz,
                'fall3':fall,'echo_u3':echo_u,'echo_v3':echo_v,
                'w3':self.resolved_ascent(u,v)+plume_updraft[None]*self.plume_fraction[None],
                'p3':self.p/100}
