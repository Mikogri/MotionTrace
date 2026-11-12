const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();const element=()=>({value:'',checked:false,children:[],add(x){this.children.push(x)},append(...x){this.children.push(...x)},replaceChildren(){this.children=[]},pause(){},currentTime:0});
const sandbox={window:{DATASET:{dataset_id:'test',videos:[{id:'a',source:'a.mp4',name:'a',exercise:'deadlift',timestamps:[0,.033,.066,.1],video:'a.mp4'}]}},document:{getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)},createElement:element},localStorage:{getItem(){return null},setItem(){}},Option:function(t,v){this.text=t;this.value=v},setTimeout,console};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(__dirname+'/review.js','utf8'),sandbox);
assert.equal(vm.runInContext('frameAt(.05)',sandbox),1);
vm.runInContext("state.records[0].reps=[{lifting_start:{frame:0,time:0},lifting_end:{frame:1,time:.033},lowering_start:{frame:2,time:.066},lowering_end:{frame:3,time:.1}}];validate(state)",sandbox);
assert.throws(()=>vm.runInContext('state.records[0].reps[0].lowering_start={frame:0,time:0};validate(state)',sandbox));
assert.throws(()=>vm.runInContext('state.records[0].reps[0].lowering_start={frame:2,time:.07};validate(state)',sandbox));
console.log('Phase review: frame lookup, deadlift ordering and timestamp validation passed.');
