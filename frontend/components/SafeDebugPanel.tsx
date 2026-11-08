/** Fail closed: technical diagnostics need a real server authorization boundary. */
export default function SafeDebugPanel(){
 return <p className="text-xs text-slate-500" data-testid="debug-unavailable">Debug diagnostics ยังไม่เปิดใช้งานจนกว่าจะมีระบบยืนยันตัวตนและตรวจสิทธิ์</p>;
}
