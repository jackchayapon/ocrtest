import {test,expect} from "@playwright/test";
import {highlightUnits} from "../lib/highlight-units";

test("Thai tone and vowel substitutions highlight the entire visible cluster",()=>{
 const units=highlightUnits([{kind:"equal",text:"ก"},{kind:"substitution",text:"ิ",missing:"ี"},{kind:"equal",text:"่"}]);
 expect(units).toHaveLength(1);
 expect(units[0].text).toBe("กิ่");
 expect(units[0].errors[0].missing).toBe("ี");
});
test("missing combining mark highlights its base; missing words use a clickable gap",()=>{
 const units=highlightUnits([{kind:"equal",text:"กา"},{kind:"deletion",text:"",missing:"่"},{kind:"deletion",text:"",missing:"ABC"}]);
 expect(units.find(u=>u.text==="า")?.errors[0].missing).toBe("่");
 expect(units.at(-1)).toEqual({text:"▏",errors:[{kind:"deletion",text:"",missing:"ABC"}]});
});
