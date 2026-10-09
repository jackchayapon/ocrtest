import type {FieldComparison} from "@/types";
type Span = FieldComparison["spans"][number];

/** Project the saved normalized alignment onto original GT lines; never re-diff OCR. */
export function errorAnalysisLines(evaluation: FieldComparison, groundTruth: string) {
 const raw=groundTruth.normalize("NFC").replace(/\r\n?/g,"\n");
 const lines=raw.split("\n").map(gt=>({gt,spans:[] as Span[]}));
 // New CER aligns non-whitespace characters. Restore GT spacing for readability,
 // without introducing whitespace errors or changing the saved alignment.
 if(raw.replace(/\s/gu,"")===evaluation.normalized_ground_truth){
  const owners:number[]=[],spaces:string[]=[];
  let row=0,pending="";
  for(const char of Array.from(raw)){
   if(char==="\n"){row++;pending="";continue;}
   if(/\s/u.test(char)){pending+=char;continue;}
   owners.push(row);spaces.push(pending);pending="";
  }
  let cursor=0,lastSpace=-1;
  for(const span of evaluation.spans){
   const units=Array.from(span.kind==="deletion"?span.missing??"":span.text);
   const missing=Array.from(span.missing??"");
   units.forEach((unit,index)=>{
    const owner=owners[cursor]??owners[owners.length-1]??0;
    if(lastSpace!==cursor&&spaces[cursor]){
     lines[owner].spans.push({kind:"equal",text:spaces[cursor]});lastSpace=cursor;
    }
    lines[owner].spans.push({kind:span.kind,text:span.kind==="deletion"?"":unit,missing:span.kind==="deletion"?unit:missing[index]});
    if(span.kind!=="insertion")cursor++;
   });
  }
  return lines;
 }
 const normalized:string[]=[],owners:number[]=[];
 let line=0,pendingSpace=false,spaceLine=0;
 for(const char of Array.from(raw)){
  if(/\s/u.test(char)){
   if(normalized.length&&!pendingSpace){pendingSpace=true;spaceLine=line;}
   if(char==="\n")line++;
   continue;
  }
  if(pendingSpace){normalized.push(" ");owners.push(spaceLine);pendingSpace=false;}
  normalized.push(char);owners.push(line);
 }
 if(normalized.join("")!==evaluation.normalized_ground_truth)return null;
 let cursor=0;
 for(const span of evaluation.spans){
  const units=span.kind==="deletion"?Array.from(span.missing??""):Array.from(span.text);
  const missing=Array.from(span.missing??"");
  for(let i=0;i<units.length;i++){
   const owner=owners[cursor]??owners[owners.length-1]??0;
   // A matching separator between GT lines is represented by the row boundary.
   const separator=span.kind==="equal"&&units[i]===" "&&owners[cursor+1]!==undefined&&owners[cursor+1]!==owner;
   if(!separator)lines[owner].spans.push({kind:span.kind,text:span.kind==="deletion"?"":units[i],missing:span.kind==="deletion"?units[i]:missing[i]});
   if(span.kind!=="insertion")cursor++;
  }
 }
 return lines;
}
