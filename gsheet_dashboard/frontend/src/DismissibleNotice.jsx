import React, {useState} from 'react';
import {createPortal} from 'react-dom';
import {X} from 'lucide-react';

const dismissedThisSession=new Set();
function notificationStack(){
  let stack=document.getElementById('workspace-notifications');
  if(!stack){stack=document.createElement('div');stack.id='workspace-notifications';stack.className='workspace-notifications';stack.setAttribute('aria-label','Notifications');document.body.appendChild(stack);}
  return stack;
}
export default function DismissibleNotice({children, noticeId, className='notice', ...props}){
  const [dismissed,setDismissed]=useState(()=>dismissedThisSession.has(noticeId));
  if(dismissed)return null;
  return createPortal(<div role="status" {...props} className={`${className} dismissible-notice`}><div className="notification-body">{children}</div><button type="button" className="icon-button" aria-label="Dismiss notification" onClick={()=>{dismissedThisSession.add(noticeId);setDismissed(true);}}><X size={16}/></button></div>,notificationStack());
}
