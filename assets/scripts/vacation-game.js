/* Worker-owned game clock; all state persists locally on static hosting. */
(function(root){
 'use strict';
 const STEP=600,END=72*3600;
 const schedule=day=>({first:3600+(day-1)*86400,second:14400+(day-1)*86400,deadline:41400+(day-1)*86400});
 function settle(d){
  const s=schedule(d.day),homework=d.first==='write'||d.second==='makeup'||d.repentAt!==null;
  const correct=homework?!d.red:d.red;
  const value=d.repentAt!==null?Math.round(667*Math.max(0,1-(d.repentAt-s.second)/(s.deadline-s.second))):d.second==='makeup'?667:1000;
  const caption=!correct?'Mission Failed':!homework&&d.red?'暖区，简单！':d.first==='skip'&&homework&&!d.red?'好险，活过来了':'';
  return {day:d.day,at:s.deadline,homework,red:d.red,redAt:d.redAt,repentAt:d.repentAt,correct,points:correct?value:0,caption,outcome:correct?'complete':'failed'};
 }
 class Game{
  constructor(saved=null){
   this.t=-STEP;this.pending=null;this.days=[1,2,3].map(day=>({day,first:null,second:null,repentAt:null,red:false,redAt:null,result:null}));
   if(saved){
    if(saved.schema!==2||!Number.isSafeInteger(saved.t)||saved.t<0||saved.t%STEP||!Array.isArray(saved.days)||saved.days.length!==3)throw Error('作业挑战存档损坏');
    if(saved.days.some((d,i)=>d.day!==i+1||![null,'write','skip'].includes(d.first)||![null,'makeup','sleep','awake'].includes(d.second)||(d.repentAt!==null&&(!Number.isSafeInteger(d.repentAt)||d.repentAt<schedule(d.day).second||d.repentAt>=schedule(d.day).deadline))))throw Error('作业选择存档损坏');
    this.t=saved.t;this.days=structuredClone(saved.days);this.pending=structuredClone(saved.pending);
    if(this.pending){const s=schedule(this.pending.day);if(![1,2,3].includes(this.pending.day)||!['first','second'].includes(this.pending.stage)||s[this.pending.stage]!==this.t)throw Error('决策时刻存档损坏');}
   }
  }
  update(t,warning){
   if(t===this.t)return this.view();if(this.pending)throw Error('必须先完成作业决策');
   if(t!==this.t+STEP)throw Error('作业挑战需要连续十分钟时钟');this.t=t;
   for(const d of this.days){const s=schedule(d.day);
    if(t===s.first&&!d.first)this.pending={day:d.day,stage:'first',at:t};
    if(t===s.second&&d.first==='skip'&&!d.second)this.pending={day:d.day,stage:'second',at:t};
    if(t>=s.second&&t<=s.deadline&&warning?.level===3){d.red=true;d.redAt??=t;}
    if(t===s.deadline&&!d.result){if(!d.first||(d.first==='skip'&&!d.second))throw Error('当日作业决策缺失');d.result=settle(d);}
   }return this.view();
  }
  choose(day,stage,choice){
   const allowed=stage==='first'?['write','skip']:['makeup','sleep','awake'];
   if(!this.pending||day!==this.pending.day||stage!==this.pending.stage||!allowed.includes(choice))throw Error('此决策已失效，请使用当前决策');
   const d=this.days[day-1];if(d[stage]!==null)throw Error('不能重复提交决策');d[stage]=choice;this.pending=null;return this.view();
  }
  repent(day,at){
   const d=this.days[day-1],s=schedule(day);
   // Use the frame the player could actually see. At most two frames of Worker
   // lookahead may exist, and an undisplayed 07:30 result can be amended once.
   if(!d||d.second!=='awake'||d.repentAt!==null||!Number.isSafeInteger(at)||at%STEP||at<s.second||at>=s.deadline||at>this.t||this.t-at>1200||this.t>s.deadline)throw Error('当前不能补作业');
   d.repentAt=at;if(d.result)d.result=settle(d);return this.view();
  }
  view(){const days=structuredClone(this.days),allSettled=days.every(d=>d.result),total=days.reduce((s,d)=>s+(d.result?.points||0),0);return {t:this.t,pending:structuredClone(this.pending),days,total,allSettled,finished:this.t>=END};}
  checkpoint(){return {schema:2,t:this.t,pending:structuredClone(this.pending),days:structuredClone(this.days)};}
 }
 const api={Game,schedule,END};root.VacationGame=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
