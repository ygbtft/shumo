"""Q3 candidate selection with full polygon reception and optional minimax bounds."""
import math
import numpy as np
from geometry import minimum_circle
from intelligent import candidate_points,hypotheses,guaranteed_omni
from signal_minimax import reception_certificate,posterior_radius_upper
from efficient_joint_policy import EfficientJointPolicy
from policies import Policy


class SafeSensingPolicy(EfficientJointPolicy):
    def __init__(self,*args,ranker="covariance",expanded=False,sensing_weight=.08,minimax_bins=2.,**kwargs):
        super().__init__(*args,**kwargs)
        if self.mixed:raise ValueError("Full range certificate alone requires an omnidirectional source")
        self.ranker,self.expanded,self.sensing_weight,self.minimax_bins=ranker,expanded,sensing_weight,minimax_bins
        self.stats.update(new_reception_candidate_accepts=0,minimax_candidate_evaluations=0,second_point_choices=[])

    def second_point(self,ch):
        poly=self.regions[ch];observations=self.observations[ch];current=np.asarray(self.client.position)
        center,radius=self.circle(ch);first,angle=observations[0];theta=math.radians(angle)
        u=np.array([math.cos(theta),math.sin(theta)]);v=np.array([-u[1],u[0]])
        points=list(candidate_points(poly,observations,current))
        if self.expanded:
            width=np.clip(radius*.3,25.,250.)
            for scale in (.25,.4):
                mid=first+scale*(center-first)
                points.extend(mid+b*width*v for b in (-1.,-1/3,0.,1/3,1.))
        centered=poly-poly.mean(axis=0);covariance=centered.T@centered/max(1,len(poly))+np.eye(2)*.01
        samples=hypotheses(poly);rows=[]
        for q in points:
            if np.linalg.norm(q-current)<=1. or any(np.linalg.norm(q-p)<=1. for p,a in observations):continue
            certificate=reception_certificate(q,poly,first)
            if not certificate["guaranteed"]:continue
            self.stats["new_reception_candidate_accepts"]+=int(not guaranteed_omni(q,poly,first))
            delta=samples-q;distance=np.maximum(1.,np.linalg.norm(delta,axis=1));normal=np.column_stack([-delta[:,1],delta[:,0]])/distance[:,None]
            cn=normal@covariance;noise=(distance*math.radians(1.01))**2/3
            denominator=np.sum(cn*normal,axis=1)+noise
            post=covariance[None,:,:]-cn[:,:,None]*cn[:,None,:]/denominator[:,None,None]
            disc=np.maximum(0,(post[:,0,0]-post[:,1,1])**2+4*post[:,0,1]**2)
            eigen=(post[:,0,0]+post[:,1,1]+np.sqrt(disc))/2
            uncertainty=float((np.sqrt(np.maximum(0,eigen))*math.sqrt(3)).mean())
            cost=float(np.linalg.norm(q-current))/5+5
            rows.append(dict(q=q,score=uncertainty+self.sensing_weight*cost,cost=cost,certificate=certificate))
        if not rows:
            assert reception_certificate(center,poly,first)["guaranteed"]
            return center
        rows.sort(key=lambda r:r["score"])
        if self.ranker=="minimax":
            # This is minimax over a screened finite action set. Each evaluated
            # action covers all possible returned bearings; screening is still
            # heuristic and does not claim a global optimum over locations.
            rows=rows[:4]
            for row in rows:
                bound=posterior_radius_upper(poly,row["q"],self.minimax_bins)
                row["score"]=bound["radius_upper_m"]+self.sensing_weight*row["cost"]
                row["continuous_radius_upper_m"]=bound["radius_upper_m"]
                self.stats["minimax_candidate_evaluations"]+=1
            rows.sort(key=lambda r:r["score"])
        best=rows[0]
        self.stats["second_point_choices"].append(dict(channel=ch,point=best["q"].tolist(),ranker=self.ranker,
            continuous_radius_upper_m=best.get("continuous_radius_upper_m"),move_measure_s=best["cost"]))
        return best["q"]

    def complete_source(self,ch):
        if ch in self.cleared:return
        for step in range(self.max_active):
            center,radius=self.circle(ch)
            if radius<=20.-1e-5:
                if not self.clear(center,ch,True):raise RuntimeError("Certified clear failed")
                return
            if radius<=self.trial_radius and ch not in self._trial_done:
                self._trial_done.add(ch);self.stats["early_optical_trials"]+=1
                if self.clear(center,ch):self.stats["early_optical_success"]+=1;return
                q=center
            else:q=self.second_point(ch)
            self.stats["active_measurements"]+=1;result=self.measure(q,ch)
            self.stats["active_no_signal"]+=int(result=="no_signal")
            if ch in self.cleared:return
            if result=="no_signal":break
        self.active=False
        try:Policy.complete_source(self,ch)
        finally:self.active=True
