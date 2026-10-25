const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../static/Reservation/js/tab-motion.js'),'utf8');
function setup(reduced=false,sidebar=false){
 const events={}, timers=new Map(), navigations=[]; let next=0;
 const items=[0,1,2].map((i)=>({offsetLeft:4+i*84,offsetTop:4,offsetWidth:80,offsetHeight:32,dataset:{},
  href:`https://campus.test/manage/facilities/?state=${i}`,origin:'https://campus.test',pathname:'/manage/facilities/',target:'',
  matches:()=>i===0,hasAttribute:()=>false}));
 const props={}; const list={matches:()=>sidebar,querySelectorAll:()=>items,contains:item=>items.includes(item),style:{setProperty:(k,v)=>props[k]=v},classList:{add:()=>{}}};
 const window={addEventListener:(name,fn)=>events[name]=fn};
 vm.runInNewContext(code,{window,document:{querySelectorAll:()=>[list]},location:{origin:'https://campus.test',pathname:'/manage/facilities/',href:items[0].href,assign:url=>navigations.push(url)},
  getComputedStyle:()=>({getPropertyValue:()=> '140ms'}),matchMedia:()=>({matches:reduced}),
  setTimeout:(fn,ms)=>{timers.set(++next,{fn,ms});return next;},clearTimeout:id=>timers.delete(id)});
 const click=(index,extra={})=>{let prevented=false;events.click({button:0,target:{closest:()=>items[index]},preventDefault:()=>prevented=true,...extra});return prevented;};
 return {events,timers,navigations,items,props,click};
}
test('directory waits for shared motion duration before navigating, then pageshow restores server selection',()=>{
 const q=setup(); assert.equal(q.click(1),true);assert.equal(q.items[1].dataset.pillSelected,'true');assert.equal(q.navigations.length,0);
 const job=[...q.timers.values()][0];assert.equal(job.ms,140);job.fn();assert.deepEqual(q.navigations,[q.items[1].href]);
 q.events.pageshow();assert.equal(q.items[0].dataset.pillSelected,'true');assert.equal(q.timers.size,0);
});
test('modified clicks and navigation already blocked by another guard remain untouched',()=>{
 for(const extra of [{ctrlKey:true},{metaKey:true},{shiftKey:true},{altKey:true},{button:1},{defaultPrevented:true}]){
  const q=setup(); assert.equal(q.click(1,extra),false);assert.equal(q.timers.size,0);assert.equal(q.navigations.length,0);
 }
});
test('rapid selection only navigates to the final tab; reselecting current destination cancels navigation',()=>{
 const q=setup();q.click(1);q.click(2);assert.equal(q.timers.size,1);[...q.timers.values()][0].fn();assert.deepEqual(q.navigations,[q.items[2].href]);
 const r=setup();r.click(1);r.click(0);assert.equal(r.timers.size,0);assert.equal(r.items[0].dataset.pillSelected,'true');
});
test('reduced motion navigates immediately without a timer',()=>{
 const q=setup(true);q.click(2);assert.equal(q.timers.size,0);assert.deepEqual(q.navigations,[q.items[2].href]);
});
test('new-window, download and unrelated destinations keep native navigation',()=>{
 for(const change of [{target:'_blank'},{hasAttribute:()=>true},{origin:'https://other.test'},{pathname:'/manage/categories/'}]){
  const q=setup();Object.assign(q.items[1],change);assert.equal(q.click(1),false);assert.equal(q.timers.size,0);
 }
});

test('both sidebar selectors allow cross-page links using the same transition and active-class selection',()=>{
 const q=setup(false,true);q.items[1].pathname='/manage/reports/';q.items[1].href='https://campus.test/manage/reports/';
 assert.equal(q.click(1),true);assert.equal(q.items[1].dataset.pillSelected,'true');
 const job=[...q.timers.values()][0];assert.equal(job.ms,140);job.fn();assert.deepEqual(q.navigations,[q.items[1].href]);
});
test('sidebar modal links retain their existing editor behaviour without moving the highlight',()=>{
 const q=setup(false,true);q.items[1].hasAttribute=name=>name==='data-edit-dialog';
 assert.equal(q.click(1),false);assert.equal(q.timers.size,0);assert.equal(q.items[0].dataset.pillSelected,'true');
});
