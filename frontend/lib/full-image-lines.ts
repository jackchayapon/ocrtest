import type {TestCase} from '@/types';

export const textLines=(text:string)=>text.replace(/\r\n?/g,'\n').split('\n');

export function isFullImageCase(record:TestCase){
 const fields=record.global_fields??[];
 if(record.workflow!=='global'||fields.length!==1)return false;
 const roi=fields[0].roi;
 return roi.x1===0&&roi.y1===0&&roi.x2===record.document.width&&roi.y2===record.document.height;
}
