import React, {useState} from 'react';
import {X} from 'lucide-react';

const dismissedThisSession=new Set();
export default function DismissibleNotice({children, noticeId, className='notice', ...props}){
  const [dismissed,setDismissed]=useState(()=>dismissedThisSession.has(noticeId));
  if(dismissed)return null;
  return <div {...props} className={`${className} dismissible-notice`}><div className="notification-body">{children}</div><button type="button" className="icon-button" aria-label="Dismiss notification" onClick={()=>{dismissedThisSession.add(noticeId);setDismissed(true);}}><X size={16}/></button></div>;
}
