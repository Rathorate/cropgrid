"use client";
import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

export default function PasswordField({name,label,minLength=10,autoComplete="new-password"}:{name:string;label:string;minLength?:number;autoComplete?:string}) {
  const [show,setShow]=useState(false);
  return <div className="passwordField"><label htmlFor={name}>{label}</label><div className="passwordControl">
    <input id={name} name={name} required type={show?"text":"password"} minLength={minLength} maxLength={128} autoComplete={autoComplete} spellCheck={false} autoCapitalize="none"/>
    <button className="passwordToggle" type="button" aria-label={`${show?"Hide":"Show"} ${label.toLowerCase()}`} aria-controls={name} aria-pressed={show} onClick={()=>setShow(!show)}>{show?<EyeOff size={18} aria-hidden="true"/>:<Eye size={18} aria-hidden="true"/>}<span>{show?"Hide":"Show"}</span></button>
  </div></div>;
}
