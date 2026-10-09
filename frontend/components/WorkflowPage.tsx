"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
import {getTestCase} from "@/lib/api";
import type {TestCase} from "@/types";
import type {WorkflowStage} from "./WorkflowSteps";
import GlobalWorkspace from "./GlobalWorkspace";
function WorkflowLoader({id,stage}:{id:string;stage:WorkflowStage}){
 const [saved,setSaved]=useState<TestCase|null>(null),[error,setError]=useState("");
 useEffect(()=>{let alive=true;getTestCase(id).then(c=>{if(alive)setSaved(c);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[id,stage]);
 if(error)return <p role="alert">{error}</p>;
 if(!saved)return <p role="status">กำลังโหลด…</p>;
 if(saved.workflow!=="global")return <Link href={`/test/${id}`}>เปิดประวัติแบบเดิม</Link>;
 return <GlobalWorkspace key={`${id}:${stage}`} initialCase={saved} stage={stage}/>;
}
export default function WorkflowPage({id,stage}:{id:string;stage:WorkflowStage}){
 return <WorkflowLoader key={`${id}:${stage}`} id={id} stage={stage}/>;
}
