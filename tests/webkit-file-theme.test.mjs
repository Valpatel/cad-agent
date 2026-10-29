import assert from 'node:assert/strict';
import test from 'node:test';
import {normalizeFileTheme} from '../src/cadagent/webkit/file-viewer-theme.js';

test('theme configuration keeps product colors outside the toolkit',()=>{
  assert.equal(normalizeFileTheme().mode,'dark');
  for(const mode of ['light','dark','auto'])assert.equal(normalizeFileTheme(mode).mode,mode);
  const original={mode:'light',colors:{accent:'#126D58',surface:'#ffffff'},fontFamily:'Inter, sans-serif'};
  const result=normalizeFileTheme(original);result.colors.accent='#000000';
  assert.equal(original.colors.accent,'#126D58');
});
test('malformed updates fail before changing a mounted viewer',()=>{
  for(const value of [null,[],2,'sepia',{mode:'invalid'},{brand:'product'},
    {colors:[]},{colors:{surfac:'#ffffff'}},{colors:{accent:'red'}},
    {colors:{accent:'#fff; color:red'}},{fontFamily:''},{fontFamily:2}]){
    assert.throws(()=>normalizeFileTheme(value),TypeError);
  }
});
