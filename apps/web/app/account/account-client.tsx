"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Sprout } from "lucide-react";
import PasswordField from "./password-field";
type Mode = "login" | "register" | "forgot" | "reset" | "change";
const titles: Record<Mode,string> = {login:"Welcome back",register:"Create your account",forgot:"Forgot your password?",reset:"Choose a new password",change:"Change your password"};
const labels: Record<Mode,string> = {login:"Sign in",register:"Create account",forgot:"Send reset link",reset:"Reset password",change:"Update password"};
const descriptions: Record<Mode,string> = {
  login:"Sign in to continue to your CropGrid workspace.",
  register:"Join as a buyer or seller to trade agricultural produce.",
  forgot:"Enter your registered email. We will send a link to verify it is you.",
  reset:"Choose a password of at least 10 characters. Your link expires after 20 minutes.",
  change:"While signed in, confirm your current password and choose a new one."
};
function apiBase() {
  const configured=process.env.NEXT_PUBLIC_API_URL;
  if(configured)return configured.replace(/\/$/,"");
  if(typeof window!=="undefined" && ["localhost","127.0.0.1"].includes(window.location.hostname))return "http://localhost:8002";
  return "";
}
export default function AccountPage(){
  const [mode,setMode]=useState<Mode>("login"),[token,setToken]=useState(""),[error,setError]=useState(""),[notice,setNotice]=useState(""),[busy,setBusy]=useState(false),[role,setRole]=useState("BUYER");
  useEffect(()=>{
    const query=new URLSearchParams(window.location.search);
    if(query.get("role")==="SELLER")setRole("SELLER");
    if(query.get("mode")==="change-password")setMode("change");
    const value=new URLSearchParams(window.location.hash.slice(1)).get("reset_token");
    if(value){setToken(value);setMode("reset");window.history.replaceState(null,"",window.location.pathname);}
  },[]);
  function switchMode(next:Mode){setMode(next);setError("");setNotice("");}
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(busy)return;setError("");setNotice("");
    const api=apiBase();if(!api){setError("The API URL is not configured for this site.");return;}
    const form=new FormData(event.currentTarget);
    if(["register","reset","change"].includes(mode)){
      const password=String(form.get(mode==="register"?"password":"new_password")||"");
      if(!password.trim()){setError("Choose a password containing more than spaces.");return;}
      if(password!==form.get("confirm_password")){setError("The passwords do not match.");return;}
    }
    if(mode==="reset"&&!token){setError("Open the reset link from your email, or request a new one.");return;}
    const paths:Record<Mode,string>={login:"login",register:"register",forgot:"forgot-password",reset:"reset-password",change:"change-password"};
    let body:Record<string,unknown>;
    if(mode==="register")body={full_name:form.get("full_name"),email:form.get("email"),password:form.get("password"),role};
    else if(mode==="login")body={email:form.get("email"),password:form.get("password")};
    else if(mode==="forgot")body={email:form.get("email")};
    else body={new_password:form.get("new_password"),confirm_password:form.get("confirm_password"),...(mode==="reset"?{token}:{current_password:form.get("current_password")})};
    setBusy(true);
    try{
      const response=await fetch(`${api}/api/v1/auth/${paths[mode]}`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      const result=await response.json().catch(()=>({}));
      if(!response.ok){
        if(response.status===401&&mode==="change")throw new Error("Sign in first, then use Change password from the marketplace header.");
        throw new Error(typeof result.detail==="string"?result.detail:"Check the form fields and try again.");
      }
      if(mode==="login"||mode==="register"){window.location.assign("/");return;}
      setNotice(result.message||"Request completed.");
      if(mode==="reset"||mode==="change"){setToken("");setMode("login");}
    }catch(caught){setError(caught instanceof Error?caught.message:"Could not connect to CropGrid.");}
    finally{setBusy(false);}
  }
  return <main className="accountPage"><section className="accountCard">
    <Link className="accountBrand" href="/"><span><Sprout size={20}/></span> CropGrid</Link>
    <p className="eyebrow label">CROPGRID MARKETPLACE</p><h1>{titles[mode]}</h1><p className="accountIntro">{descriptions[mode]}</p>
    <form key={mode} onSubmit={submit} className="accountForm"><fieldset disabled={busy} className="accountFields">
      {mode==="register"&&<label>Full name<input name="full_name" required minLength={2} maxLength={120} autoComplete="name"/></label>}
      {["login","register","forgot"].includes(mode)&&<label>Email<input name="email" type="email" required maxLength={254} autoComplete="email"/></label>}
      {(mode==="login"||mode==="register")&&<PasswordField name="password" label="Password" minLength={mode==="register"?10:1} autoComplete={mode==="register"?"new-password":"current-password"}/>}
      {mode==="change"&&<PasswordField name="current_password" label="Current password" minLength={1} autoComplete="current-password"/>}
      {(mode==="reset"||mode==="change")&&<PasswordField name="new_password" label="New password"/>}
      {["register","reset","change"].includes(mode)&&<><PasswordField name="confirm_password" label="Confirm password"/><small>Use at least 10 characters. A password manager can help you choose a strong password.</small></>}
      {mode==="register"&&<label>Account type<select value={role} onChange={e=>setRole(e.target.value)}><option value="BUYER">Buyer</option><option value="SELLER">Seller</option></select></label>}
      {error&&<div className="formerror" role="alert">{error}</div>}{notice&&<div className="accountNotice" role="status">{notice}</div>}
      <button className="primary" disabled={busy}>{busy?"Please wait…":labels[mode]}</button>
    </fieldset></form>
    {mode==="login"&&<p className="accountSwitch"><button type="button" disabled={busy} onClick={()=>switchMode("forgot")}>Forgot password?</button></p>}
    <p className="accountSwitch">{mode==="login"?"New to CropGrid?":mode==="register"?"Already registered?":"Remember your password?"} <button disabled={busy} onClick={()=>switchMode(mode==="login"?"register":"login")}>{mode==="login"?"Create account":"Sign in"}</button></p>
    {mode==="login"&&<p className="accountSwitch"><button disabled={busy} onClick={()=>switchMode("change")}>Change password while signed in</button></p>}
    {mode==="register"&&<p className="accountAdminNote">Admin accounts are created by the system owner and cannot be selected during public registration.</p>}
    <Link className="accountBack" href="/">← Return to marketplace</Link>
  </section></main>;
}
