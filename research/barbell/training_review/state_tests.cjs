// Unit checks of annotation state/export; no browser or user storage is accessed.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('research/barbell/training_review/review.js','utf8');
const html=fs.readFileSync('research/barbell/training_review/review.html','utf8');
const data={schema:1,dataset_id:'unit-test',annotation_coordinates:'pixels',videos:[],tasks:[1,2].map(n=>({id:String(n),video_id:'v',video_name:'test.mp4',image:'unused.jpg',timestamp:n,width:720,height:1280,shaft_segments:[],shaft_visibility:'unknown',review_status:'unreviewed',notes:''}))};
const store=new Map([['motiontrace-shaft-v1','previous-review-untouched']]);let exported;
function setup(){const nodes={};const make=()=>({value:'',textContent:'',style:{},children:[],files:[],append(x){this.children.push(x)},replaceChildren(){this.children=[]},setAttribute(k,v){this[k]=v},getBoundingClientRect(){return{left:10,top:20,width:360,height:640}},click(){}});
for(const m of html.matchAll(/id="([^"]+)"/g))nodes[m[1]]=make();nodes.zoom.value='1';
const context={window:{DATASET:data},document:{getElementById:id=>nodes[id],createElement:()=>make(),createElementNS:()=>make()},localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},structuredClone,Blob,URL:{createObjectURL:b=>{exported=b;return'blob:test'},revokeObjectURL(){}},setTimeout:fn=>fn()};vm.runInNewContext(code,context);return nodes}
(async()=>{
let n=setup();n.approve.onclick();assert.match(n.message.textContent,/Sprawdź/);assert.equal(n.progress.value,0);
n.draw.onclick({clientX:110,clientY:220});n.draw.onclick({clientX:210,clientY:225});
let saved=JSON.parse(store.get('motiontrace-unit-test'));assert.deepEqual(saved.tasks[0].shaft_segments,[[200,400,400,410]]);
n.visibility.value='occluded';n.visibility.onchange();n.approve.onclick();
assert.equal(n.progress.value,0);assert.match(n.message.textContent,/masz 1 odcinków/);
saved=JSON.parse(store.get('motiontrace-unit-test'));assert.deepEqual(saved.tasks[0].shaft_segments,[[200,400,400,410]]);assert.equal(saved.tasks[0].review_status,'edited');
n.export.onclick();const partial=JSON.parse(await exported.text());assert.equal(partial.tasks[0].review_status,'edited');assert.deepEqual(partial.tasks[0].shaft_segments,[[200,400,400,410]]);
n.visibility.value='partial';n.visibility.onchange();
n.approve.onclick();assert.equal(n.progress.value,1);assert.equal(n.count.textContent,'2 / 2');
n=setup();assert.equal(n.count.textContent,'2 / 2');assert.equal(n.progress.value,1);
n.visibility.value='absent';n.visibility.onchange();n.approve.onclick();assert.equal(n.progress.value,2);
n.export.onclick();const result=JSON.parse(await exported.text());assert.equal(result.tasks.length,2);assert.equal(result.tasks[0].review_status,'approved');assert.equal(result.tasks[1].shaft_visibility,'absent');
const bad=structuredClone(result);bad.tasks[0].notes='must not partially import';bad.tasks[1].shaft_segments=[[0,0,9999,0]];
n.import.files=[{text:async()=>JSON.stringify(bad)}];await n.import.onchange({target:n.import});assert.match(n.message.textContent,/Nie wczytano/);
n.export.onclick();assert.equal(JSON.parse(await exported.text()).tasks[0].notes,'');
assert.equal(store.get('motiontrace-shaft-v1'),'previous-review-untouched');
console.log('PASS: pixel mapping, approval validation, auto-next, reload persistence, one full JSON export, atomic invalid-import rejection, previous-batch storage isolation.');
})().catch(e=>{console.error(e);process.exitCode=1});
