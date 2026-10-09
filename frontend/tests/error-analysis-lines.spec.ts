import {test,expect} from "@playwright/test";
import type {FieldComparison} from "../types";
import {errorAnalysisLines} from "../lib/error-analysis-lines";

function evaluation(reference:string,spans:FieldComparison["spans"]){return {normalized_ground_truth:reference,spans} as FieldComparison;}
test("saved errors follow GT lines, including blank lines and multiline deletions",()=>{
 const result=errorAnalysisLines(evaluation("AB CD EF",[
  {kind:"equal",text:"A"},{kind:"substitution",text:"X",missing:"B"},
  {kind:"equal",text:" "},{kind:"deletion",text:"",missing:"CD"},
  {kind:"equal",text:" EF"},{kind:"insertion",text:"!"},
 ]),"AB\r\n\r\nCD\nEF")!;
 expect(result.map(l=>l.gt)).toEqual(["AB","","CD","EF"]);
 expect(result[0].spans.map(s=>s.text).join("")).toBe("AX");
 expect(result[1].spans).toEqual([]);
 expect(result[2].spans.map(s=>s.missing).join("")).toBe("CD");
 expect(result[3].spans.map(s=>s.text).join("")).toBe("EF!");
});
test("NFC, indentation and Unicode codepoints retain correct line ownership",()=>{
 const result=errorAnalysisLines(evaluation("é 😀 ไทย",[{kind:"equal",text:"é 😀 ไทย"}]),"  e\u0301\n😀\nไทย  ")!;
 expect(result.map(l=>l.spans.map(s=>s.text).join(""))).toEqual(["é","😀","ไทย"]);
});
test("stale GT cannot be assigned to the saved alignment",()=>{
 expect(errorAnalysisLines(evaluation("old",[{kind:"equal",text:"old"}]),"new")).toBeNull();
});

test("whitespace-free CER restores GT spacing and line ownership without space errors",()=>{
 const result=errorAnalysisLines(evaluation("ABCD",[
  {kind:"equal",text:"AB"},{kind:"substitution",text:"X",missing:"C"},
  {kind:"deletion",text:"",missing:"D"},
 ]),"A B\n\nC D")!;
 expect(result.map(l=>l.gt)).toEqual(["A B","","C D"]);
 expect(result.map(l=>l.spans.map(s=>s.text).join(""))).toEqual(["A B","","X "]);
 expect(result.flatMap(l=>l.spans).filter(s=>s.kind!=="equal")).toHaveLength(2);
});
