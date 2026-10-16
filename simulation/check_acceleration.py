"""Browser-only bitwise comparison of fused and reference transport."""
import numpy as np
from . import numerics
from . import thermo
from .core import Model
from .terrain import grid


def check(*,include_model=True):
    callback=numerics._accelerator
    if callback is None:raise RuntimeError('Browser accelerator is not installed')
    moist_callback=thermo._accelerator
    rng=np.random.default_rng(412);cases=0;thermal_cases=0;thermal_error=0.
    try:
        for shape in [(9,13),(3,9,13)]:
            for dtype in [np.float32,np.float64]:
                # Include signed source moments, not only positive water.
                a=(rng.random(shape)-.5).astype('float64')
                u=rng.normal(4,5,shape).astype(dtype);v=rng.normal(-2,4,shape).astype(dtype)
                for boundary in [None,0,.02,np.asarray(0,dtype='float64'),np.asarray(.02,dtype='float32'),np.asarray(0,dtype='int64'),rng.random(shape)]:
                    for conservative in [False,True]:
                        operator=numerics.Advection(u,v,1000)
                        numerics.install_accelerator(None);expected=operator(a,20,boundary,conservative)
                        numerics.install_accelerator(callback);actual=operator(a,20,boundary,conservative)
                        np.testing.assert_array_equal(actual,expected)
                        saved=actual.copy();operator(a*.5,20,boundary,conservative)
                        np.testing.assert_array_equal(actual,saved);cases+=1
        for kind in ['surface','mixed','unstable']:
            p=np.broadcast_to((101000*np.exp(-np.arange(14)*.14))[:,None,None],(14,9,13)).copy()
            t=300-8000*.0065*(-np.log(p/101000));q=thermo.saturation(294,101000)*np.exp(np.log(p/101000)*8000/2300)
            t+=rng.normal(0,.3,t.shape)
            thermo.install_accelerator(None);expected=thermo.parcel(p,t,q,kind)
            thermo.install_accelerator(moist_callback);actual=thermo.parcel(p,t,q,kind)
            for key in ['cape','cin','path']:
                np.testing.assert_allclose(actual[key],expected[key],rtol=1e-10,atol=1e-8)
                thermal_error=max(thermal_error,float(np.max(abs(actual[key]-expected[key]))))
            thermal_cases+=1
        if not include_model:
            return {'flux_cases':cases,'flux_exact':True,'parcel_cases':thermal_cases,'thermal_max_abs_error':thermal_error,'model_steps':0}
        cfg={'bounds':[112,22,113.5,24],'grid_km':10,'seed':719}
        lon,lat=grid(cfg['bounds'],cfg['grid_km']);height=np.where(lon>112.8,0,30)
        thermo.install_accelerator(None);reference=Model(cfg,height)
        thermo.install_accelerator(moist_callback);accelerated=Model(cfg,height)
        for model in [reference,accelerated]:
            # Exercise the actual ice/moment/tag chain even before this small
            # environment has naturally initiated its first storm.
            model.cloud[9,:,model.shape[1]//2]=.0008
            model.plume_cloud[9,:,model.shape[1]//2]=.0008
        for _ in range(40):
            numerics.install_accelerator(None);thermo.install_accelerator(None);reference.step()
            numerics.install_accelerator(callback);thermo.install_accelerator(moist_callback);accelerated.step()
        fields=['temp','q','cloud','rain','anvil','anvil_nx','anvil_ny','anvil_motion','stratiform_rain','last_stratiform_rate','plume_cloud','plume_rain','rain_area','total','u','v','syn_u','syn_v','air','cold_content','cold_depth','cold_mx','cold_my','activity','surface_activity','organization','cape_deficit','synoptic_lift','ground_temp','transported_wake_debt']
        fields+=['graupel','graupel_area','plume_cloud_area','momentum_u','momentum_v','downburst_energy']
        for key in fields:np.testing.assert_allclose(getattr(reference,key),getattr(accelerated,key),rtol=1e-8,atol=1e-8,err_msg=key)
        if not np.any(reference.anvil):raise AssertionError('Ice comparison did not exercise the new reservoir')
        return {'flux_cases':cases,'flux_exact':True,'parcel_cases':thermal_cases,'thermal_max_abs_error':thermal_error,'model_steps':40,'model_fields':len(fields),'model_tolerance':1e-8}
    finally:numerics.install_accelerator(callback);thermo.install_accelerator(moist_callback)
