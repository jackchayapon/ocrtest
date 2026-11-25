import styles from './LoadingHand.module.css';

/** Decorative CSS animation; progress and timing come from the evaluation UI. */
export default function LoadingHand(){
 return <div className={styles.panel} aria-hidden="true" data-testid="loading-hand">
  <svg className={styles.hand} viewBox="0 0 260 190" focusable="false">
   <g fill="white">
    {[{x:12,y:43,h:102},{x:60,y:36,h:123},{x:108,y:31,h:142},{x:156,y:48,h:127}].map(({x,y,h})=><g key={x} className={styles.finger}>
     <rect x={x} y={y} width="43" height={h} rx="16"/>
     <path d={`M${x+12} ${y+8}h19`} stroke="#acbaff" strokeWidth="5"/>
     <rect x={x+7} y={y+h-37} width="29" height="30" rx="13" fill="#a7b5ff"/>
    </g>)}
    <path className={styles.thumb} d="M204 83 C220 98 237 79 247 92 C263 117 238 139 204 133 Z"/>
   </g>
  </svg>
 </div>;
}
