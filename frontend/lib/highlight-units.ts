import type {FieldComparison} from "@/types";
type Span=FieldComparison["spans"][number];
export type HighlightUnit={text:string;errors:Span[]};

// Segment for display only. The backend's code-point edit counts stay unchanged.
export function highlightUnits(spans:Span[]):HighlightUnit[]{
 const text=spans.map(s=>s.text).join("");
 const units=Array.from(new Intl.Segmenter("th",{granularity:"grapheme"}).segment(text),s=>({text:s.segment,start:s.index,end:s.index+s.segment.length,errors:[] as Span[]}));
 const gaps:{position:number;span:Span}[]=[];
 let offset=0;
 for(const span of spans){
  if(span.kind==="deletion"){
   // Missing Thai combining marks belong to the preceding visible glyph.
   const previous=units.find(u=>u.start<offset&&u.end>=offset);
   if(previous&&/^\p{M}+$/u.test(span.missing??""))previous.errors.push(span);
   else gaps.push({position:offset,span});
  }else{
   if(span.kind!=="equal")for(const unit of units)if(unit.start<offset+span.text.length&&unit.end>offset)unit.errors.push(span);
   offset+=span.text.length;
  }
 }
 const result:HighlightUnit[]=[];
 for(const unit of units){
  for(const gap of gaps.filter(g=>g.position>=unit.start&&g.position<unit.end))result.push({text:"▏",errors:[gap.span]});
  const last=result.at(-1);
  if(!unit.errors.length&&last&&!last.errors.length)last.text+=unit.text;
  else result.push({text:unit.text,errors:unit.errors});
 }
 for(const gap of gaps.filter(g=>g.position>=text.length))result.push({text:"▏",errors:[gap.span]});
 return result;
}
