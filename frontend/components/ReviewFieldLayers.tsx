"use client";
import {memo,useCallback,useEffect,useLayoutEffect,useMemo,useRef} from 'react';
import type Konva from 'konva';
import {Group,Layer,Rect} from 'react-konva';
import type {ROI} from '@/types';
import FieldLabel from './FieldLabel';

type Field={id:string;field_index:number;roi:ROI;placeholder?:boolean};
type Props={fields:Field[];x:number;y:number;scale:number;selected?:string|null;showFields:boolean;showLabels:boolean;interactive:boolean;color?:string;missing:string[];errors:string[];mismatches:string[];onSelect?:(id:string)=>void};
type Drawing=Field&{color:string;error:boolean;label:string};

// The base canvas has no selection dependency. Konva retains its nodes while
// selection changes redraw only the small, non-interactive highlight layer.
const FixedLayer=memo(function FixedLayer({fields,x,y,scale,showFields,showLabels,interactive,onSelect}:{fields:Drawing[];x:number;y:number;scale:number;showFields:boolean;showLabels:boolean;interactive:boolean;onSelect:(id:string)=>void}){
 const group=useRef<Konva.Group>(null);
 useLayoutEffect(()=>{
  const node=group.current;if(!node||!fields.length)return;
  const bounds=node.getClientRect({skipTransform:true});
  if(bounds.width<=0||bounds.height<=0)return;
  // Cache at display resolution, bounded for large scans. Translation is
  // deliberately absent from dependencies: dragging reuses scene + hit maps.
  const ratio=Math.min(scale*(window.devicePixelRatio||1),2,8192/bounds.width,8192/bounds.height,Math.sqrt(4_000_000/(bounds.width*bounds.height)));
  node.cache({pixelRatio:ratio,hitCanvasPixelRatio:ratio});
  return()=>{node.clearCache();};
 },[fields,scale,showFields,showLabels,interactive]);
 return <Layer name="fixed-review-fields"><Group ref={group} x={x} y={y} scaleX={scale} scaleY={scale}>
  {fields.map(field=><Group key={field.id} name="global-layout-field" listening={interactive&&!field.placeholder} onClick={()=>onSelect(field.id)} onTap={()=>onSelect(field.id)}>
   <Rect x={field.roi.x1} y={field.roi.y1} width={field.roi.x2-field.roi.x1} height={field.roi.y2-field.roi.y1} stroke={showFields||field.placeholder?field.color:undefined} strokeWidth={1.25} strokeScaleEnabled={false} dash={field.placeholder?[6/scale,3/scale]:field.error?[5/scale,3/scale]:undefined} fill={field.placeholder?'rgba(250,204,21,0.16)':'rgba(0,0,0,0)'}/>
   {showLabels&&showFields&&<FieldLabel x={field.roi.x1} y={field.roi.y1} scale={scale} text={field.label} color={field.color}/>}
  </Group>)}
 </Group></Layer>;
});

export default function ReviewFieldLayers(props:Props){
 const callback=useRef(props.onSelect);
 useEffect(()=>{callback.current=props.onSelect;},[props.onSelect]);
 const select=useCallback((id:string)=>callback.current?.(id),[]);
 // Parents often recreate arrays during typing/selection; compare their data,
 // not object identity, so unchanged geometry never rebuilds the base layer.
 const signature=JSON.stringify(props.fields.map(field=>({...field,
  color:field.placeholder?'#ca8a04':props.mismatches.includes(field.id)||props.missing.includes(field.id)?'#dc2626':props.errors.includes(field.id)?'#b45309':props.color??'#2563eb',
  error:props.errors.includes(field.id),
  label:`Field ${String(field.field_index).padStart(2,'0')}${props.missing.includes(field.id)?' · ไม่มี GT':''}${props.errors.includes(field.id)?' · OCR error':''}`,
 })));
 const fields=useMemo(()=>JSON.parse(signature) as Drawing[],[signature]);
 const selected=fields.find(field=>field.id===props.selected&&!field.placeholder);
 return <>
  <FixedLayer fields={fields} x={props.x} y={props.y} scale={props.scale} showFields={props.showFields} showLabels={props.showLabels} interactive={props.interactive} onSelect={select}/>
  <Layer name="selected-review-field" listening={false}><Group x={props.x} y={props.y} scaleX={props.scale} scaleY={props.scale}>
   {selected&&<Group><Rect x={selected.roi.x1} y={selected.roi.y1} width={selected.roi.x2-selected.roi.x1} height={selected.roi.y2-selected.roi.y1} stroke="#6d28d9" strokeWidth={2} strokeScaleEnabled={false} fill="rgba(109,40,217,0.12)"/>
    {props.showLabels&&<FieldLabel x={selected.roi.x1} y={selected.roi.y1} scale={props.scale} text={`${selected.label} •`} color="#6d28d9"/>}
   </Group>}
  </Group></Layer>
 </>;
}
