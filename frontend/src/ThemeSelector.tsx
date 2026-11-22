import {useEffect,useState} from 'react';

export function ThemeSelector(){
  const [theme,setTheme]=useState<'light'|'dark'>(()=>localStorage.getItem('opspilot-theme')==='dark'?'dark':'light');
  useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('opspilot-theme',theme)},[theme]);
  return <label className="demo">APPEARANCE <select aria-label="Appearance" value={theme} onChange={e=>setTheme(e.target.value as 'light'|'dark')}><option value="light">Light</option><option value="dark">Dark</option></select></label>;
}
