import {test,expect} from "@playwright/test";
import {highlightUnits} from "../lib/highlight-units";

test("Thai tone and vowel substitutions highlight the entire visible cluster",()=>{
 const units=highlightUnits([{kind:"equal",text:"ก"},{kind:"substitution",text:"ิ",missing:"ี"},{kind:"equal",text:"่"}]);
 expect(units).toHaveLength(1);
 expect(units[0].text).toBe("กิ่");
 expect(units[0].errors[0].missing).toBe("ี");
});

test("mixed Thai combining marks, English/numbers and trailing deletions preserve every error",()=>{
 const spans=[{kind:"deletion" as const,text:"",missing:"ิ"},{kind:"equal" as const,text:"😀 ก"},{kind:"substitution" as const,text:"้",missing:"่"},{kind:"equal" as const,text:" A"},{kind:"insertion" as const,text:"2"},{kind:"deletion" as const,text:"",missing:" B"}];
 const units=highlightUnits(spans);
 const errors=units.flatMap(u=>u.errors);
 expect(errors).toHaveLength(4);
 expect(errors.map(e=>e.kind).sort()).toEqual(["deletion","deletion","insertion","substitution"]);
 expect(units.filter(u=>u.text==="▏")).toHaveLength(2);
 expect(units.find(u=>u.errors.some(e=>e.kind==="substitution"))?.text).toBe("ก้");
});
test("missing combining mark highlights its base; missing words use a clickable gap",()=>{
 const units=highlightUnits([{kind:"equal",text:"กา"},{kind:"deletion",text:"",missing:"่"},{kind:"deletion",text:"",missing:"ABC"}]);
 expect(units.find(u=>u.text==="า")?.errors[0].missing).toBe("่");
 expect(units.at(-1)).toEqual({text:"▏",errors:[{kind:"deletion",text:"",missing:"ABC"}]});
});
