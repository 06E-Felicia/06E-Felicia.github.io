"""Seeded, evolving synoptic boundary forcing for the reduced column model.

This is not a primitive-equation forecast. The external cold-air reservoir,
pressure-wave trajectory and geostrophic wave are scenario boundary forcing;
rain, plumes and cold pools remain prognostic and are never painted here.
"""
import math
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates


class SynopticDriver:
    COASTAL_DELAY_SECONDS = 12 * 3600

    def __init__(self, cfg, lon, lat, terrain):
        self.cfg=cfg;self.lon=lon;self.lat=lat
        self.terrain=gaussian_filter(np.maximum(terrain,0),max(.5,24/cfg['grid_km']))
        self.inflow_resistance=np.ones(lon.shape[1])
        rng=np.random.default_rng(np.random.SeedSequence([int(cfg['seed']),3917]))
        self.regime=['coupled','west','east','mixed'][int(rng.integers(4))]
        self.phase=float(rng.uniform(-1,1))
        self.period=float(rng.uniform(25,37))*3600
        self.tilt=float(rng.uniform(-.3,.3))
        self.center=float(rng.uniform(22.8,23.6))
        self.wave_phase=float(rng.uniform(0,2*math.pi))
        self.phase_speed=float(rng.uniform(.42,.6))
        self.front_lat=np.full(lon.shape[1],cfg['bounds'][3]+.4)
        self.front_lat+=.10*np.sin((lon[0]-110)/1.7+self.phase)
        # Add twelve hours of upstream travel at the slow, pre-Nanling
        # reservoir speed. The front keeps moving from outside the domain;
        # neither its terrain/inflow response nor the warm-sector clock is
        # paused. Coastal arrival is delayed approximately, not prescribed
        # at a fixed hour regardless of the seeded environment.
        self.front_lat+=(1.45*math.sqrt(cfg['cold_reservoir'])*self.regional_pattern()
                         *self.COASTAL_DELAY_SECONDS/111195)
        # Diagnose a regional crest, not every local hill. Outside a cropped
        # mechanism-test domain retain the geographical Nanling reference.
        mask=(lat>=24.3)&(lat<=25.8)
        relief=np.where(mask,terrain,-1)
        index=np.argmax(relief,axis=0)
        crest=lat[index,np.arange(lon.shape[1])]
        exists=np.max(relief,axis=0)>250
        self.crest=gaussian_filter1d(np.where(exists,crest,25.15),max(.5,70/cfg['grid_km']))
        self.front_speed=np.zeros(lon.shape[1])
        self.bay_lon=float(rng.uniform(87,91))
        self.bay_lat=float(rng.uniform(16,19))
        self.genesis_rng=np.random.default_rng(np.random.SeedSequence([int(cfg['seed']),73118]))
        self.genesis_start=float(self.genesis_rng.uniform(.5,1.5))*3600
        self.genesis_duration=float(self.genesis_rng.uniform(6,8))*3600
        self.genesis_center=None
        self.episode_index=0

    def configure_genesis(self,cape,cin,lfc,height,*,fresh=None,episode=0):
        """One finite confluence episode, not a prescribed storm/rain object.

        Select a favourable western warm-sector sounding. Only pressure-flow
        forcing and first-initiation permission are prescribed; parcels must
        still overcome CIN/LFC and pay their real air/water/energy budgets.
        """
        from scipy.ndimage import gaussian_filter
        if episode!=self.episode_index:
            self.episode_index=episode
            self.genesis_start=episode*86400+float(self.genesis_rng.uniform(.5,1.5))*3600
            self.genesis_duration=float(self.genesis_rng.uniform(6,8))*3600
        eligible=(self.lon>106.8)&(self.lon<110)&(self.lat>22)&(self.lat<23.8)&(height<600)&(cape>300)&np.isfinite(lfc)
        if fresh is not None:eligible&=fresh
        if not eligible.any():
            eligible=(cape>150)&np.isfinite(lfc)
            if fresh is not None:eligible&=fresh
        if not eligible.any():
            self.genesis_center=None;return
        score=gaussian_filter(np.maximum(cape,0)*np.exp(np.minimum(cin,0)/80)/np.maximum(lfc,500),max(.5,35/self.cfg['grid_km']))
        score*=self.genesis_rng.uniform(.75,1.25,score.shape)
        score=np.where(eligible,score,-1)
        iy,ix=np.unravel_index(np.argmax(score),score.shape)
        self.genesis_center=(float(self.lon[iy,ix]),float(self.lat[iy,ix]))
        self.genesis_half_length=float(self.genesis_rng.uniform(95,135))*1000
        self.genesis_speed=float(self.genesis_rng.uniform(10,12))

    def genesis(self,time):
        if self.genesis_center is None:return np.zeros_like(self.lon),np.zeros_like(self.lon)
        phase=(time-self.genesis_start)/self.genesis_duration
        if not 0<phase<1:return np.zeros_like(self.lon),np.zeros_like(self.lon)
        lon,lat=self.genesis_center
        x=(self.lon-lon)*111195*math.cos(math.radians(lat))
        y=(self.lat-lat)*111195
        envelope=np.exp(-(x/80000)**2-(y/self.genesis_half_length)**4)
        pulse=math.sin(math.pi*phase)**2
        # Broad finite convergence feeds a few noisy thermals on ONE boundary.
        # It ends once per episode. A new day needs a NEW sounding/fresh-air
        # assessment; this pulse never repeats automatically in the old wake.
        flow=-self.genesis_speed*np.tanh(x/18000)*envelope*pulse
        permission=np.clip((envelope-.25)/.5,0,1)
        return flow,permission

    def regional_pattern(self):
        x=self.lon[0]
        if self.regime=='west':p=np.exp(-((x-108-self.phase)/3.8)**2)
        elif self.regime=='east':p=np.exp(-((x-114.5-self.phase)/3.8)**2)
        elif self.regime=='mixed':p=.5+.5*np.cos((x-111-self.phase)/1.7)
        else:p=np.full_like(x,.5)
        return .9+.2*p

    def speed(self,time):
        # Pressure-driven motion persists after the short wave passes. A
        # smooth lee acceleration follows actual crest crossing; no timer
        # stops the Guangdong half of the reservoir behind the Guangxi half.
        crossed=.5*(1+np.tanh((self.crest-.20-self.front_lat)/.30))
        pressure=math.sqrt(self.cfg['cold_reservoir'])
        wave=1+.10*math.sin(time/self.period*2*math.pi+self.wave_phase)
        # The pre-crest reservoir must not sweep the second day's warm
        # inflow away before its mesoscale convergence develops. Retain slow
        # continuous motion, then a geographically diagnosed lee surge.
        # Work against the LOCAL upcoming barrier, not just one regional
        # ridge-crossing switch. Valleys lead while high ridges retard flow.
        local=self.sample_front(self.terrain)
        ahead=np.maximum(self.sample_front(self.terrain,20000),self.sample_front(self.terrain,40000))
        barrier=np.maximum(ahead-local,0)
        inside=(self.front_lat<=self.cfg['bounds'][3])&(self.front_lat>=self.cfg['bounds'][1])
        terrain_drag=np.where(inside,1/(1+.7*barrier/650),1)
        return ((1.45+6.5*crossed)*pressure*self.regional_pattern()*wave
                *terrain_drag*getattr(self,'inflow_resistance',1))

    def sample_front(self,field,ahead=0):
        # Latitude increases with row index. Positive ahead points south into
        # the warm sector; no wrapping or off-domain terrain is invented.
        row=(self.front_lat-ahead/111195-self.lat[0,0])/(self.lat[1,0]-self.lat[0,0])
        return map_coordinates(field,[row,np.arange(self.lon.shape[1])],order=1,mode='nearest')

    def advance(self,dt,time,warm_u=None,warm_v=None):
        along=np.zeros_like(self.front_lat)
        if warm_u is not None and warm_v is not None:
            # Sample actual resolved SYNOPTIC warm flow, not thunderstorm
            # gusts. The mean scenario speed already balances its reference
            # 5*jet inflow; departures from it create local advance/retardation.
            # Stay outside the front's own 70-km pressure footprint: sampling
            # its weakened near-frontal inflow created a self-acceleration.
            along=self.sample_front(warm_u,120000)
            north=self.sample_front(warm_v,120000)
            slope=np.gradient(self.front_lat*111195,self.cfg['grid_km']*1000)
            opposing=(north-along*slope)/np.sqrt(1+slope*slope)
            self.inflow_resistance=np.clip(1/np.maximum(.5,1+.06*(opposing-5*self.cfg['jet'])),.65,1.35)
        self.front_speed=self.speed(time+dt/2)
        x=np.arange(len(self.front_lat))
        departed=x-along*dt/(self.cfg['grid_km']*1000)
        self.front_lat=np.interp(departed,x,self.front_lat)-self.front_speed*dt/111195
        # Along-front pressure adjustment communicates a provincial lead/lag
        # rather than letting a small initial speed difference grow forever.
        # Regional 220-km / 3-h smoothing erased precisely the terrain and
        # inflow bends being computed above. Communicate only shorter-scale
        # pressure differences, more slowly, without straightening the front.
        smooth=gaussian_filter1d(self.front_lat,max(.5,50/self.cfg['grid_km']))
        self.front_lat+=(smooth-self.front_lat)*(-math.expm1(-dt/43200))

    def external_air(self):
        return 1/(1+np.exp(np.clip(-(self.lat-self.front_lat[None])*111195/18000,-40,40)))

    def surface_target(self,air,time):
        speed=self.speed(time)[None]
        external=self.external_air()
        # Confluence translates with the pressure wave. Opposing inflows at
        # air=.5 must NOT cancel the front's own southward propagation.
        # The old 130-km pressure footprint also removed the warm LLJ far
        # ahead of the actual front, effectively advancing it a second time.
        influence=np.maximum(external,np.exp(-((self.lat-self.front_lat[None])*111195/70000)**2))
        u=4*(1-air)+air
        v=5*self.cfg['jet']*(1-air)*(1-influence)
        v+=influence*(4*(1-2*np.maximum(air,external))-speed)
        confluence,_=self.genesis(time)
        u+=confluence
        return u,v

    def wave(self,time,trough_lon):
        # The parent southern-branch trough stays over the Bay of Bengal.
        # South China samples its broad DOWNSTREAM flow, not a local short
        # wave sweeping through the computational domain every few hours.
        phase=2*math.pi*time/self.period+self.wave_phase
        center=self.bay_lat+.25*math.sin(phase)
        axis=self.bay_lon+.6*math.sin(phase*.35)+self.tilt*(self.lat-center)
        x=(self.lon-axis)/18
        y=(self.lat-center)/12
        envelope=np.exp(-.5*(x*x+y*y))
        strength=self.cfg['trough']*(.85+.15*math.sin(2*math.pi*time/self.period+self.wave_phase))
        return x,y,envelope,strength

    def free_winds(self,z,time,trough_lon,noise):
        c=self.cfg;x,y,envelope,strength=self.wave(time,trough_lon)
        # A tilted, finite geostrophic streamfunction trough: southerly ahead,
        # northerly behind, with the matching zonal perturbation. NOT a fixed
        # meridional wind ribbon or a storm-length/reflectivity mask.
        wave_z=np.exp(-((z-5600)/3000)**2)
        # South China is the far downstream flank, not the trough's strong
        # meridional core. Previously this perturbation plus an independent
        # southerly background turned 500-hPa steering toward the northeast.
        amplitude=4*strength*envelope
        ratio=18*math.cos(math.radians(self.bay_lat))/12
        wu=amplitude*(self.tilt*math.cos(math.radians(self.center))*x-ratio*y)
        wv=amplitude*x
        phase=2*math.pi*time/self.period+self.wave_phase
        axis=25.8+.7*np.sin((self.lon-self.bay_lon)/10+phase*.35)
        jet_shape=np.exp(-((self.lat-axis)/3.8)**2)
        jet_strength=18*c['shear']*(1+.16*math.sin(phase)+.06*np.tanh(noise))
        upper=jet_strength*jet_shape*np.exp(-((z-10500)/3300)**2)
        background=9+z*.003*c['shear']+upper
        angle=.08+.045*math.sin(phase)+.025*np.tanh(noise)
        u=background+wu[None]*wave_z
        v=background*np.tan(angle)[None]+wv[None]*wave_z
        # Time/space-varying southwesterly 925-hPa jet; the diurnal cycle is
        # not the only evolution. Its axis/angle respond to the travelling wave.
        hour=(8+time/3600)%24
        nocturnal=.90+.25*math.cos((hour-4)*2*math.pi/24)
        llj=14*c['jet']*nocturnal*(1+.15*np.tanh(x)*envelope+.06*np.tanh(noise))
        llj*=.8+.2*np.exp(-((self.lat-23.4)/2.4)**2)
        angle=.90+.12*np.tanh(x)*envelope+.18*math.sin(phase)+.06*math.cos(phase*.7)
        vertical=np.exp(-((z-1000)/700)**2)
        return u,v,llj[None]*np.cos(angle)[None]*vertical,llj[None]*np.sin(angle)[None]*vertical

    def ascent(self,time,trough_lon):
        x,y,envelope,strength=self.wave(time,trough_lon)
        # Broad downstream differential-advection proxy, negative behind the
        # trough. Subsidence dries/warms the trailing region after passage.
        # Weak regional ascent conditions the warm sector; it is insufficient
        # by itself to act as a domain-wide deep-convection elevator.
        return .025*strength*x*envelope
