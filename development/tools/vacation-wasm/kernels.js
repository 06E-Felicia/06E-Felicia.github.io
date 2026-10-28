/* Numeric source for the deliberately non-optimizing scalar WAT build. i_* are i32 addresses/indices; all other locals are f64. V/S load/store binary64. */
function finite(x){return abs(x)<=1.7976931348623157e308;}
function validate(i_p,i_n,i_nonnegative){for(let i_k=0;i_k<i_n;i_k++){let x=V(i_p,i_k);if(!finite(x))return 1;if(i_nonnegative&&x< -1e-8)return 2;}return 0;}
function bank_add(i_b,i_slot,x){S(i_b,i_slot,V(i_b,i_slot)+x);if(V(i_b,64+i_slot)===0){S(i_b,64+i_slot,1);let i_count=T(V(i_b,192));S(i_b,128+i_count,i_slot);S(i_b,192,i_count+1);}}
function vector_predict(i_s,i_rhs,i_out,i_start,i_end,dt){for(let i_k=i_start;i_k<i_end;i_k++)S(i_out,i_k,V(i_s,i_k)+dt*V(i_rhs,i_k));}
function vector_correct(i_s,i_stage,i_rhs,i_out,i_start,i_end,dt){for(let i_k=i_start;i_k<i_end;i_k++)S(i_out,i_k,.5*(V(i_s,i_k)+V(i_stage,i_k)+dt*V(i_rhs,i_k)));}
function precip_rhs(i_nx,i_ny,dx,i_a,i_u,i_v,i_out,i_start,i_end,i_axis,i_loss){let loss=V(i_loss,0);for(let i_f=i_start;i_f<i_end;i_f++){let i_i=0,i_j=0,i_l=0,i_r=0,vel=0;if(i_axis===0){i_j=i_f/(i_nx+1);i_i=i_f%(i_nx+1);i_l=i_i?i_j*i_nx+i_i-1:-1;i_r=i_i<i_nx?i_j*i_nx+i_i:-1;vel=V(i_u,i_f);}else{i_j=i_f/i_nx;i_i=i_f%i_nx;i_l=i_j?(i_j-1)*i_nx+i_i:-1;i_r=i_j<i_ny?i_j*i_nx+i_i:-1;vel=V(i_v,i_f);}let i_d=vel>=0?i_l:i_r,flux=i_d<0?0:vel*V(i_a,i_d);if(i_l>=0)S(i_out,i_l,V(i_out,i_l)-flux/dx);if(i_r>=0)S(i_out,i_r,V(i_out,i_r)+flux/dx);if(i_l<0)loss-=flux*dx;if(i_r<0)loss+=flux*dx;}S(i_loss,0,loss);}
/* P SoA order: qa,upper_core,lower_core,upper_detrained,lower_detrained,upper_boundary,lower_boundary. coefficients qa,keMid,rateMid,factorMid,keLow,rateLow,factorLow,cascadeRemaining. */
function precip_collect(i_n,i_en,i_rn,area,rainArea,qaFraction,i_start,i_end,i_p,i_env,i_req,i_dl,i_dm,i_coeff,i_targets,i_areas,i_rain,i_conv,i_marks,i_touch,i_bank){
 for(let i_k=i_start;i_k<i_end;i_k++){
  let i_e=T(V(i_env,i_k));if(i_e<0||i_e>=i_en)return 3;
  let sum=V(i_p,i_k)+V(i_p,i_n+i_k)+V(i_p,2*i_n+i_k)+V(i_p,3*i_n+i_k)+V(i_p,4*i_n+i_k)+V(i_p,5*i_n+i_k)+V(i_p,6*i_n+i_k);if(sum===0)continue;
  let converted=max(V(i_p,i_k)-.1,0)*qaFraction;S(i_p,i_k,V(i_p,i_k)-converted);S(i_p,3*i_n+i_k,V(i_p,3*i_n+i_k)+converted);
  let mass=V(i_p,i_k)*V(i_coeff,i_e)*area;if(!finite(mass))return 1;if(mass>0){S(i_dm,i_e,V(i_dm,i_e)+mass);S(i_req,i_k*7,mass);}
  for(let i_o=0;i_o<3;i_o++){
   let i_up=(1+2*i_o)*i_n+i_k,i_low=(2+2*i_o)*i_n+i_k;if(V(i_p,i_up)+V(i_p,i_low)===0)continue;
   let source=i_o===0?V(i_p,7*i_n+i_k):0,oldUpper=max(0,V(i_p,i_up)-source),oldLower=V(i_p,i_low),kf=1/300,keM=V(i_coeff,i_en+i_e),upperRate=i_o===1?V(i_coeff,10*i_en+i_e):V(i_coeff,2*i_en+i_e),upperFall=i_o===1?V(i_coeff,13*i_en+i_e):kf,upperFactor=i_o===1?V(i_coeff,11*i_en+i_e):V(i_coeff,3*i_en+i_e),outUpper=oldUpper*upperFactor+source*(1-V(i_coeff,8*i_en+i_e)),fall=outUpper*upperFall/upperRate,evapUpper=outUpper*keM/upperRate;S(i_p,i_up,V(i_p,i_up)-fall);S(i_p,i_low,V(i_p,i_low)+fall);mass=evapUpper*area;if(!finite(mass))return 1;if(mass>0){S(i_dm,i_e,V(i_dm,i_e)+mass);S(i_req,i_k*7+1+2*i_o,mass);}
   let ke=V(i_coeff,4*i_en+i_e),rate=V(i_coeff,5*i_en+i_e),out=max(0,oldLower+fall-(oldLower*(1-V(i_coeff,6*i_en+i_e))+oldUpper*(i_o===1?V(i_coeff,12*i_en+i_e):V(i_coeff,7*i_en+i_e))+source*V(i_coeff,9*i_en+i_e))),ground=out*kf/rate,evap=out*ke/rate;S(i_p,i_low,V(i_p,i_low)-ground);
   if(ground>0){mass=ground*area;if(!finite(mass)||mass< -1e-8)return 1;bank_add(i_bank,i_o,mass);bank_add(i_bank,3+i_o,mass);bank_add(i_bank,6+i_o,mass);
    for(let i_q=i_k*4;i_q<i_k*4+4;i_q++){let i_r=T(V(i_targets,i_q));if(i_r<0||i_r>=i_rn)return 3;let rainMass=ground*V(i_areas,i_q);S(i_rain,i_r,V(i_rain,i_r)+rainMass/rainArea);if(i_o===0)S(i_conv,i_r,V(i_conv,i_r)+rainMass/rainArea);if(V(i_marks,i_r)===0){S(i_marks,i_r,1);let i_count=T(V(i_touch,i_rn));S(i_touch,i_count,i_r);S(i_touch,i_rn,i_count+1);}bank_add(i_bank,9,rainMass);}
   }
   mass=evap*area;if(!finite(mass))return 1;if(mass>0){S(i_dl,i_e,V(i_dl,i_e)+mass);S(i_req,i_k*7+2+2*i_o,mass);}
  }
 }return 0;
}
/* Accounting bank: each origin total,Mid,Low,ColdHeat slots0..11; origin ledgerOut12..14; Mid/Low flows15..20. */
function precip_account(i_n,i_en,area,alpha,i_disable,i_start,i_end,i_p,i_env,i_req,i_low,i_mid,i_bank){
 for(let i_k=i_start;i_k<i_end;i_k++){let i_e=T(V(i_env,i_k));if(i_e<0||i_e>=i_en)return 3;for(let i_q=0;i_q<7;i_q++){
  let mass=V(i_req,i_k*7+i_q);if(mass<=0)continue;let i_o=i_q===0?1:(i_q-1)/2,i_lowLevel=i_q!==0&&i_q%2===0,i_index=i_q*i_n+i_k,used=mass*(i_lowLevel?V(i_low,i_e):V(i_mid,i_e));S(i_p,i_index,V(i_p,i_index)-used/area);bank_add(i_bank,4*i_o,used);bank_add(i_bank,4*i_o+(i_lowLevel?2:1),used);if(!finite(used)||used< -1e-8)return 1;if(used>0){bank_add(i_bank,12+i_o,used);bank_add(i_bank,15+2*i_o+(i_lowLevel?1:0),used);}if(i_lowLevel&&!i_disable)bank_add(i_bank,4*i_o+3,alpha*used);
 }}return 0;
}
function cold_sample(i_s,i_z,i_k,i_n,zGhost,i_out){if(i_k<0){for(let i_q=0;i_q<9;i_q++)S(i_out,i_q,0);S(i_out,8,zGhost);return;}let A=V(i_s,i_n+i_k)/2.5;S(i_out,0,V(i_s,i_k));S(i_out,1,V(i_s,i_n+i_k));S(i_out,2,A>=1e-8?V(i_s,2*i_n+i_k):0);S(i_out,3,A>=1e-8?V(i_s,3*i_n+i_k):0);S(i_out,4,A);S(i_out,5,A>=1e-8?V(i_s,2*i_n+i_k)/A:0);S(i_out,6,A>=1e-8?V(i_s,3*i_n+i_k)/A:0);S(i_out,8,V(i_z,i_k));}
function cold_reconstruct(i_src,i_out,z,G){let A=max(0,V(i_src,4)+V(i_src,8)-z),ratio=V(i_src,4)>0?A/V(i_src,4):1;S(i_out,0,V(i_src,0)*ratio);S(i_out,1,2.5*A);S(i_out,2,V(i_src,2)*ratio);S(i_out,3,V(i_src,3)*ratio);S(i_out,4,A);S(i_out,5,V(i_src,5));S(i_out,6,V(i_src,6));S(i_out,7,.5*G*A*A);S(i_out,8,V(i_src,8));}
function cold_faces(i_nx,i_ny,dx,G,i_boundary,i_axis,i_start,i_end,i_s,i_z,i_wind,i_out,i_rates,i_faces,i_budget,i_scratch){
 let i_n=i_nx*i_ny,i_nf=i_axis===0?(i_nx+1)*i_ny:i_nx*(i_ny+1),i_L=i_scratch,i_R=i_scratch+72,i_a=i_scratch+144,i_b=i_scratch+216;
 for(let i_index=i_start;i_index<i_end;i_index++){
  let i_i=0,i_j=0,i_l=0,i_r=0;if(i_axis===0){i_j=i_index/(i_nx+1);i_i=i_index%(i_nx+1);if(i_boundary===2&&i_i===i_nx)continue;i_l=i_i?i_j*i_nx+i_i-1:i_boundary===2?i_j*i_nx+i_nx-1:-1;i_r=i_i<i_nx?i_j*i_nx+i_i:-1;}else{i_j=i_index/i_nx;i_i=i_index%i_nx;if(i_boundary===2&&i_j===i_ny)continue;i_l=i_j?(i_j-1)*i_nx+i_i:i_boundary===2?(i_ny-1)*i_nx+i_i:-1;i_r=i_j<i_ny?i_j*i_nx+i_i:-1;}
  S(i_budget,9,V(i_budget,9)+1);
  let wind=V(i_wind,i_index),i_emptyL=i_l<0||(V(i_s,i_l)===0&&V(i_s,i_n+i_l)===0&&V(i_s,2*i_n+i_l)===0&&V(i_s,3*i_n+i_l)===0),i_emptyR=i_r<0||(V(i_s,i_r)===0&&V(i_s,i_n+i_r)===0&&V(i_s,2*i_n+i_r)===0&&V(i_s,3*i_n+i_r)===0),i_wall=i_boundary===1&&(i_l<0||i_r<0),i_normal=i_axis+2;
  if(i_emptyL&&i_emptyR){S(i_budget,10,V(i_budget,10)+1);let lo=i_wall?-abs(wind):wind,hi=i_wall?abs(wind):wind;S(i_faces,i_index,wind);S(i_faces,2*i_nf+i_index,lo);S(i_faces,3*i_nf+i_index,hi);if(i_l>=0)S(i_rates,i_l,V(i_rates,i_l)+max(hi,0)/dx);if(i_r>=0)S(i_rates,i_r,V(i_rates,i_r)+max(-lo,0)/dx);continue;}
  cold_sample(i_s,i_z,i_l,i_n,i_r>=0?V(i_z,i_r):0,i_L);cold_sample(i_s,i_z,i_r,i_n,i_l>=0?V(i_z,i_l):0,i_R);S(i_L,7,.5*G*V(i_L,4)*V(i_L,4));S(i_R,7,.5*G*V(i_R,4)*V(i_R,4));
  if(i_wall){let i_real=i_l>=0?i_L:i_R,i_ghost=i_l<0?i_L:i_R;for(let i_c=0;i_c<9;i_c++)S(i_ghost,i_c,V(i_real,i_c));S(i_ghost,i_axis+5,-V(i_real,i_axis+5)-2*wind);S(i_ghost,i_normal,V(i_ghost,4)*V(i_ghost,i_axis+5));}
  let z=max(V(i_L,8),V(i_R,8));cold_reconstruct(i_L,i_a,z,G);cold_reconstruct(i_R,i_b,z,G);
  let unL=wind+V(i_a,i_axis+5),unR=wind+V(i_b,i_axis+5),cL=sqrt(G*V(i_a,4)),cR=sqrt(G*V(i_b,4)),sL=min(unL-cL,unR-cR),sR=max(unL+cL,unR+cR);if(V(i_a,4)>0&&V(i_b,4)===0){sL=unL-cL;sR=unL+2*cL;}else if(V(i_b,4)>0&&V(i_a,4)===0){sL=unR-2*cR;sR=unR+cR;}
  let vn=V(i_a,4)>=1e-8&&V(i_b,4)>=1e-8?(V(i_a,i_axis+5)+V(i_b,i_axis+5))*.5:V(i_a,4)>=1e-8?V(i_a,i_axis+5):V(i_b,4)>=1e-8?V(i_b,i_axis+5):0;
  S(i_faces,i_index,wind+vn);S(i_faces,i_nf+i_index,vn);S(i_faces,2*i_nf+i_index,sL);S(i_faces,3*i_nf+i_index,sR);
  let pressure=sL>=0?V(i_a,7):sR<=0?V(i_b,7):sR>sL?(sR*V(i_a,7)-sL*V(i_b,7))/(sR-sL):0;
  for(let i_c=0;i_c<4;i_c++){
   let fl=V(i_a,i_c)*unL,fr=V(i_b,i_c)*unR,adv=sL>=0?fl:sR<=0?fr:sR>sL?(sR*fl-sL*fr+sL*sR*(V(i_b,i_c)-V(i_a,i_c)))/(sR-sL):0,i_normalComp=i_c===i_normal,F=adv+(i_normalComp?pressure:0),leftF=F+(i_normalComp?V(i_L,7)-V(i_a,7):0),rightF=F+(i_normalComp?V(i_R,7)-V(i_b,7):0);
   if(i_l>=0)S(i_out,i_c*i_n+i_l,V(i_out,i_c*i_n+i_l)-leftF/dx);if(i_r>=0)S(i_out,i_c*i_n+i_r,V(i_out,i_c*i_n+i_r)+rightF/dx);
   if(i_c===0){if(i_l<0)S(i_budget,0,V(i_budget,0)-F*dx);if(i_r<0)S(i_budget,0,V(i_budget,0)+F*dx);}if(i_c===1){if(i_l<0)S(i_budget,1,V(i_budget,1)-F*dx);if(i_r<0)S(i_budget,1,V(i_budget,1)+F*dx);}
   if(i_c>=2){S(i_budget,8,V(i_budget,8)+(abs(adv)+(i_normalComp?abs(pressure)+abs(V(i_L,7)-V(i_a,7))+abs(V(i_R,7)-V(i_b,7)):0))*dx);let i_xy=i_c-2;if(i_l<0){S(i_budget,2+i_xy,V(i_budget,2+i_xy)-adv*dx);S(i_budget,4+i_xy,V(i_budget,4+i_xy)-(i_normalComp?pressure:0)*dx);}if(i_r<0){S(i_budget,2+i_xy,V(i_budget,2+i_xy)+adv*dx);S(i_budget,4+i_xy,V(i_budget,4+i_xy)+(i_normalComp?pressure:0)*dx);}S(i_budget,6+i_xy,V(i_budget,6+i_xy)+((i_r>=0&&i_normalComp?V(i_R,7)-V(i_b,7):0)-(i_l>=0&&i_normalComp?V(i_L,7)-V(i_a,7):0))*dx);}
  }
  if(i_l>=0)S(i_rates,i_l,V(i_rates,i_l)+max(sR,0)/dx);if(i_r>=0)S(i_rates,i_r,V(i_rates,i_r)+max(-sL,0)/dx);
 }
}
function cold_rate(i_nx,i_ny,dx,G,i_start,i_end,i_s,i_u,i_v,i_rates,i_result){let i_n=i_nx*i_ny,rate=V(i_result,0);for(let i_k=i_start;i_k<i_end;i_k++){let i_i=i_k%i_nx,i_j=i_k/i_nx,A=V(i_s,i_n+i_k)/2.5,c=sqrt(G*max(A,0)),vx=A>=1e-8?V(i_s,2*i_n+i_k)/A:0,vy=A>=1e-8?V(i_s,3*i_n+i_k)/A:0,ux=.5*(V(i_u,i_j*(i_nx+1)+i_i)+V(i_u,i_j*(i_nx+1)+i_i+1))+vx,uy=.5*(V(i_v,i_j*i_nx+i_i)+V(i_v,(i_j+1)*i_nx+i_i))+vy;rate=max(max(rate,V(i_rates,i_k)),(abs(ux)+c+abs(uy)+c)/dx);}S(i_result,0,rate);}
function cold_valid(i_s,i_n,i_start,i_end){for(let i_k=i_start;i_k<i_end;i_k++){let h=V(i_s,i_k),q=V(i_s,i_n+i_k);if(h< -1e-10||q< -1e-10||q-2.5*h>1e-9)return 1;}return 0;}
function env_faces(i_nx,i_ny,dx,boundary,i_temp,factor,i_a,i_u,i_v,i_out,i_start,i_end,i_axis,i_budget){for(let i_f=i_start;i_f<i_end;i_f++){let i_i=0,i_j=0,i_l=0,i_r=0,vel=0;if(i_axis===0){i_j=i_f/(i_nx+1);i_i=i_f%(i_nx+1);i_l=i_i?i_j*i_nx+i_i-1:-1;i_r=i_i<i_nx?i_j*i_nx+i_i:-1;vel=V(i_u,i_f);}else{i_j=i_f/i_nx;i_i=i_f%i_nx;i_l=i_j?(i_j-1)*i_nx+i_i:-1;i_r=i_j<i_ny?i_j*i_nx+i_i:-1;vel=V(i_v,i_f);}let i_d=vel>=0?i_l:i_r,flux=vel*(i_d<0?boundary:V(i_a,i_d));if(i_l>=0)S(i_out,i_l,V(i_out,i_l)-flux/dx);if(i_r>=0)S(i_out,i_r,V(i_out,i_r)+flux/dx);if(i_l>=0&&i_r>=0)continue;let net=((i_l<0?-flux:0)+(i_r<0?flux:0))*dx;if(!i_temp){S(i_budget,0,V(i_budget,0)+max(-net,0));S(i_budget,1,V(i_budget,1)+max(net,0));S(i_budget,2,V(i_budget,2)+max(-net,0));S(i_budget,3,V(i_budget,3)+max(net,0));}let hnet=net*factor;S(i_budget,4,V(i_budget,4)+max(-hnet,0));S(i_budget,5,V(i_budget,5)+max(hnet,0));}}
function env_air(i_nx,i_ny,dx,i_start,i_end,i_ul,i_vl,i_um,i_vm,i_F,i_top,i_dL,i_dM,i_rate){let rate=V(i_rate,0);for(let i_k=i_start;i_k<i_end;i_k++){let i_i=i_k%i_nx,i_j=i_k/i_nx,i_l=i_j*(i_nx+1)+i_i,i_b=i_j*i_nx+i_i,dL=(V(i_ul,i_l+1)-V(i_ul,i_l)+V(i_vl,i_b+i_nx)-V(i_vl,i_b))/dx,dM=(V(i_um,i_l+1)-V(i_um,i_l)+V(i_vm,i_b+i_nx)-V(i_vm,i_b))/dx,F=-1400*dL,top=F-2600*dM,outL=max(-V(i_ul,i_l),0)+max(V(i_ul,i_l+1),0)+max(-V(i_vl,i_b),0)+max(V(i_vl,i_b+i_nx),0),outM=max(-V(i_um,i_l),0)+max(V(i_um,i_l+1),0)+max(-V(i_vm,i_b),0)+max(V(i_vm,i_b+i_nx),0);S(i_F,i_k,F);S(i_top,i_k,top);S(i_dL,i_k,dL);S(i_dM,i_k,dM);rate=max(max(rate,outL/dx+max(F,0)/1400),outM/dx+(max(-F,0)+max(top,0))/2600);}S(i_rate,0,rate);}
