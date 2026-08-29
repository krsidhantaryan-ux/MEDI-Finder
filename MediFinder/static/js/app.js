/* MediFinder — Professional core client
   Light theme, clean UX, no experimental effects
*/
(function(){
  "use strict";

  // Force light
  document.documentElement.setAttribute("data-theme","light");
  localStorage.setItem("mf-theme","light");

  // Mobile nav
  document.addEventListener("click",(e)=>{
    const toggle=e.target.closest(".burger");
    if(toggle){
      const isOpen=document.body.classList.toggle("menu-open");
      toggle.setAttribute("aria-expanded",isOpen?"true":"false");
    }else if(!e.target.closest("#site-nav") && !e.target.closest(".mobile-nav") && !e.target.closest(".burger")){
      if(document.body.classList.contains("menu-open")){
        document.body.classList.remove("menu-open");
        document.querySelectorAll(".burger").forEach(b=>b.setAttribute("aria-expanded","false"));
      }
    }
  });
  document.addEventListener("keydown",(e)=>{
    if(e.key==="Escape" && document.body.classList.contains("menu-open")){
      document.body.classList.remove("menu-open");
      const modal=document.getElementById("reserveModal");
      if(modal?.classList.contains("open")){
        modal.classList.remove("open");
        document.body.style.overflow="";
      }
    }
  });
  window.addEventListener("resize",()=>{
    if(window.matchMedia("(min-width: 900px)").matches && document.body.classList.contains("menu-open")){
      document.body.classList.remove("menu-open");
    }
  });

  // Toasts — professional light
  window.MF=window.MF||{};
  MF.toast=function(message,type="info",title){
    let wrap=document.getElementById("toastWrap");
    if(!wrap){
      wrap=document.createElement("div");
      wrap.id="toastWrap";wrap.className="toast-wrap";
      wrap.setAttribute("aria-live","polite");wrap.setAttribute("role","region");
      document.body.appendChild(wrap);
    }
    const iconMap={success:"bi-check-circle-fill",error:"bi-exclamation-triangle-fill",warning:"bi-exclamation-circle-fill",info:"bi-info-circle-fill"};
    const icon=iconMap[type]||"bi-info-circle";
    const el=document.createElement("div");
    el.className=`toast ${type}`;
    el.setAttribute("role","status");
    el.innerHTML=`<i class="bi ${icon}"></i><div>${title?`<strong>${title}</strong>`:""}<p>${message}</p></div><button class="modal-close" style="margin-left:auto;min-width:32px;min-height:32px" aria-label="Dismiss"><i class="bi bi-x"></i></button>`;
    wrap.appendChild(el);
    el.querySelector("button").addEventListener("click",()=>el.remove());
    setTimeout(()=>{
      el.style.transition="opacity .22s ease, transform .22s ease";
      el.style.opacity="0";el.style.transform="translateY(-6px)";
      setTimeout(()=>el.remove(),240);
    },4200);
  };

  // Geolocation
  MF.userPos=null;
  MF.getUserLocation=function(opts={}){
    return new Promise((resolve,reject)=>{
      if(!navigator.geolocation) return reject(new Error("Geolocation not supported"));
      navigator.geolocation.getCurrentPosition(
        pos=>{MF.userPos={lat:pos.coords.latitude,lng:pos.coords.longitude};resolve(MF.userPos);},
        err=>reject(err),
        {enableHighAccuracy:true,timeout:9000,maximumAge:60000,...opts}
      );
    });
  };
  MF.reverseGeocode=async function(lat,lng){
    try{
      const r=await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=12`);
      const d=await r.json();const a=d.address||{};
      return a.city||a.town||a.village||a.suburb||a.county||"";
    }catch{return"";}
  };

  // Map — light tiles
  MF.tileUrl=function(){
    return "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
  };
  MF.tileAttrib='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';
  MF.makeIcon=function(variant="default"){
    const glyph=variant==="user"?"":'<i class="bi bi-capsule-pill"></i>';
    const color=variant==="user"?"#0f766e":"#0f172a";
    return L.divIcon({
      className:"mf-pin",
      html:`<div class="pin"><div class="pulse" style="background:${color}"></div><div class="pin-body" style="background:${color}">${glyph}</div><div class="pin-shadow"></div></div>`,
      iconSize:[34,42],iconAnchor:[17,40],popupAnchor:[0,-36]
    });
  };
  MF.addTileLayer=function(map){
    return L.tileLayer(MF.tileUrl(),{maxZoom:19,attribution:MF.tileAttrib}).addTo(map);
  };

  // Reservation modal — professional
  let lastFocused=null;
  MF.openReserve=function(medId,medName,shopName){
    lastFocused=document.activeElement;
    let back=document.getElementById("reserveModal");
    if(!back){
      back=document.createElement("div");
      back.id="reserveModal";back.className="modal-back";back.setAttribute("role","presentation");
      back.innerHTML=`
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="reserveTitle" aria-describedby="reserveSub">
          <div class="modal-head">
            <h3 id="reserveTitle">Reserve medicine</h3>
            <button class="modal-close" data-close aria-label="Close">&times;</button>
          </div>
          <form class="modal-body" id="reserveForm" novalidate>
            <p class="small mb-3" id="reserveSub" style="color:var(--muted)"></p>
            <input type="hidden" name="med_id" id="reserveMedId">
            <div class="mb-3">
              <label class="form-label required" for="reserveName">Your name</label>
              <input type="text" name="name" id="reserveName" class="form-control" placeholder="Full name" required autocomplete="name">
              <div class="form-error" id="err-name" role="alert" hidden></div>
            </div>
            <div class="mb-3">
              <label class="form-label required" for="reservePhone">Phone number</label>
              <input type="tel" name="phone" id="reservePhone" class="form-control" placeholder="For pharmacy confirmation" required autocomplete="tel" inputmode="numeric">
              <small class="form-hint" id="phoneHelp">Shared with pharmacy only</small>
              <div class="form-error" id="err-phone" role="alert" hidden></div>
            </div>
            <div class="row mb-3" style="gap:12px">
              <div style="flex:1">
                <label class="form-label" for="reserveQty">Quantity</label>
                <input type="number" name="quantity" id="reserveQty" class="form-control" value="1" min="1" max="99" inputmode="numeric">
              </div>
            </div>
            <div class="mb-2">
              <label class="form-label" for="reserveNote">Note (optional)</label>
              <textarea name="note" id="reserveNote" class="form-control" rows="2" placeholder="e.g. I'll collect around 6 PM"></textarea>
            </div>
            <small class="form-hint"><i class="bi bi-clock-history"></i> Stock held for 2 hours. Pharmacy may call to confirm.</small>
          </form>
          <div class="modal-foot">
            <button class="btn btn-ghost" data-close>Cancel</button>
            <button class="btn btn-primary" id="reserveSubmit"><i class="bi bi-bag-check"></i> Confirm hold</button>
          </div>
        </div>`;
      document.body.appendChild(back);
      back.addEventListener("click",(e)=>{ if(e.target===back || e.target.closest("[data-close]")) closeReserve(); });
      back.querySelector("#reserveSubmit").addEventListener("click",submitReservation);
      back.addEventListener("keydown",(e)=>{
        if(e.key==="Tab"){
          const focusable=back.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
          const first=focusable[0],last=focusable[focusable.length-1];
          if(e.shiftKey && document.activeElement===first){e.preventDefault();last.focus();}
          else if(!e.shiftKey && document.activeElement===last){e.preventDefault();first.focus();}
        }
      });
    }
    document.getElementById("reserveMedId").value=medId;
    document.getElementById("reserveSub").innerHTML=`<i class="bi bi-capsule-pill" style="color:var(--primary)"></i> <strong>${medName}</strong> at <strong>${shopName}</strong>`;
    back.classList.add("open");document.body.style.overflow="hidden";
    setTimeout(()=>document.getElementById("reserveName")?.focus(),80);
  };
  function closeReserve(){
    const back=document.getElementById("reserveModal");
    if(back){back.classList.remove("open");document.body.style.overflow=""; if(lastFocused) lastFocused.focus();}
  }
  MF.closeReserve=closeReserve;
  async function submitReservation(){
    const form=document.getElementById("reserveForm");
    const data=Object.fromEntries(new FormData(form).entries());
    form.querySelectorAll(".form-error").forEach(el=>{el.hidden=true;el.textContent="";});
    form.querySelectorAll("[aria-invalid]").forEach(el=>el.removeAttribute("aria-invalid"));
    let hasError=false;
    if(!data.name || data.name.trim().length<2){
      const err=document.getElementById("err-name");err.textContent="Please enter your full name (at least 2 characters).";err.hidden=false;
      document.getElementById("reserveName").setAttribute("aria-invalid","true");hasError=true;
    }
    if(!data.phone || data.phone.trim().length<7){
      const err=document.getElementById("err-phone");err.textContent="Enter a valid phone number.";err.hidden=false;
      document.getElementById("reservePhone").setAttribute("aria-invalid","true");hasError=true;
    }
    if(hasError){MF.toast("Please fix the highlighted fields","error","Check your details");form.querySelector("[aria-invalid]")?.focus();return;}
    const btn=document.getElementById("reserveSubmit");
    btn.disabled=true;const orig=btn.innerHTML;btn.innerHTML='<i class="bi bi-hourglass-split"></i> Holding...';
    try{
      const r=await fetch("/api/reserve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
      const j=await r.json();
      if(j.ok){MF.toast(j.message,"success","Reservation confirmed");closeReserve();form.reset();document.dispatchEvent(new CustomEvent("reservation",{detail:j}));}
      else{MF.toast(j.error||"Could not reserve","error");}
    }catch{MF.toast("Network error — please try again","error");}
    finally{btn.disabled=false;btn.innerHTML=orig;}
  }

  // Favourites
  MF.toggleFavourite=async function(medName,salt,btn){
    if(btn){btn.disabled=true;}
    try{
      const r=await fetch("/api/favourites",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({med_name:medName,salt:salt||""})});
      if(r.status===401){MF.toast("Sign in to save favourites","warning");return;}
      if(r.ok){MF.toast("Saved to your medicines","success"); if(btn){btn.classList.add("active");const ic=btn.querySelector("i"); if(ic) ic.className="bi bi-bookmark-check-fill";}}
      else if(r.status===409){
        await fetch("/api/favourites",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({med_name:medName,salt:salt||""})});
        MF.toast("Removed from favourites","info");
        if(btn){btn.classList.remove("active");const ic=btn.querySelector("i"); if(ic) ic.className="bi bi-bookmark";}
      }
    }catch{MF.toast("Could not update favourites","error");}
    finally{if(btn) btn.disabled=false;}
  };

  MF.fmtMoney=function(n){const v=Number(n||0);return "₹"+v.toLocaleString("en-IN",{minimumFractionDigits:v%1?2:0,maximumFractionDigits:2});};
  MF.fmtDistance=function(km){if(km==null) return ""; if(km<1) return Math.round(km*1000)+" m away"; return km.toFixed(1)+" km away";};

  document.addEventListener("submit",(e)=>{const f=e.target.closest("form[data-confirm]"); if(f && !confirm(f.dataset.confirm)) e.preventDefault();});
})();
