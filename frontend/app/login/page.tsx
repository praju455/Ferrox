"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@ferrox.local");
  const [password, setPassword] = useState("replace-with-a-strong-password");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      router.push("/workspace");
    } catch (err: any) {
      setError(err.message || "Failed to log in");
      setLoading(false);
    }
  }

  return (
    <div style={{ 
      display: 'flex', 
      minHeight: '100vh', 
      background: 'var(--black)', 
      color: 'var(--white)', 
      alignItems: 'center', 
      justifyContent: 'center', 
      backgroundImage: 'url("/ferrox-industrial-pump.jpg")', 
      backgroundSize: 'cover', 
      backgroundPosition: '62% center' 
    }}>
      <div style={{ 
        position: 'absolute', 
        inset: 0, 
        background: 'linear-gradient(135deg, rgba(6,7,6,0.98) 0%, rgba(6,7,6,0.85) 100%)' 
      }} />
      
      <div style={{ 
        position: 'relative', 
        zIndex: 1, 
        width: '100%', 
        maxWidth: '420px', 
        padding: '48px 40px', 
        background: 'rgba(255, 255, 255, 0.03)', 
        border: '1px solid rgba(255, 255, 255, 0.1)', 
        borderRadius: '8px', 
        backdropFilter: 'blur(16px)', 
        boxShadow: '0 28px 90px rgba(0,0,0,0.48)' 
      }}>
        <div style={{ marginBottom: '36px', textAlign: 'center' }}>
          <div style={{ 
            display: 'inline-flex', 
            width: '48px', 
            height: '48px', 
            alignItems: 'center', 
            justifyContent: 'center', 
            background: 'var(--orange)', 
            color: 'var(--black)', 
            borderRadius: '2px', 
            fontSize: '18px', 
            fontWeight: 900, 
            marginBottom: '20px' 
          }}>
            F/
          </div>
          <h1 style={{ fontSize: '28px', margin: 0, fontWeight: 700, letterSpacing: '-0.5px' }}>Sign in</h1>
          <p style={{ color: '#aeb3ac', marginTop: '10px', fontSize: '15px' }}>Industrial Product Intelligence</p>
        </div>
        
        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
          {error && (
            <div style={{ 
              padding: '14px', 
              background: 'rgba(243, 109, 33, 0.12)', 
              borderLeft: '3px solid var(--orange)', 
              color: 'var(--white)', 
              fontSize: '14px',
              borderRadius: '2px'
            }}>
              {error}
            </div>
          )}
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <label style={{ fontSize: '11px', fontWeight: 700, color: '#c6c9c3', textTransform: 'uppercase', letterSpacing: '0.5px', fontFamily: '"Courier New", monospace' }}>Email Address</label>
            <input 
              type="email" 
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required 
              style={{ 
                background: 'rgba(0,0,0,0.4)', 
                border: '1px solid rgba(255,255,255,0.15)', 
                padding: '14px 16px', 
                borderRadius: '3px', 
                color: 'var(--white)', 
                outline: 'none', 
                transition: 'border-color 0.2s',
                fontSize: '15px'
              }}
              onFocus={(e) => e.target.style.borderColor = 'var(--orange)'}
              onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.15)'}
            />
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <label style={{ fontSize: '11px', fontWeight: 700, color: '#c6c9c3', textTransform: 'uppercase', letterSpacing: '0.5px', fontFamily: '"Courier New", monospace' }}>Password</label>
            <input 
              type="password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required 
              style={{ 
                background: 'rgba(0,0,0,0.4)', 
                border: '1px solid rgba(255,255,255,0.15)', 
                padding: '14px 16px', 
                borderRadius: '3px', 
                color: 'var(--white)', 
                outline: 'none', 
                transition: 'border-color 0.2s',
                fontSize: '15px'
              }}
              onFocus={(e) => e.target.style.borderColor = 'var(--orange)'}
              onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.15)'}
            />
          </div>
          
          <button 
            type="submit" 
            disabled={loading}
            style={{ 
              marginTop: '12px', 
              background: 'var(--orange)', 
              color: 'var(--black)', 
              padding: '16px', 
              border: 'none', 
              borderRadius: '3px', 
              fontSize: '15px', 
              fontWeight: 800, 
              cursor: loading ? 'not-allowed' : 'pointer', 
              opacity: loading ? 0.7 : 1, 
              transition: 'background 0.2s' 
            }}
            onMouseOver={(e) => !loading && (e.currentTarget.style.background = '#ff8a46')}
            onMouseOut={(e) => !loading && (e.currentTarget.style.background = 'var(--orange)')}
          >
            {loading ? "Authenticating..." : "Access Workspace"}
          </button>
        </form>
      </div>
    </div>
  );
}
