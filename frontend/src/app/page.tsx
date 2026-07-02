"use client";

import { useEffect, useState } from "react";
import { Users, Activity, Video, ShieldCheck, VideoOff, Wifi, WifiOff } from "lucide-react";

export default function Dashboard() {
  const [gateStatus, setGateStatus] = useState("CLOSED");
  const [usersCount, setUsersCount] = useState(0);
  const [recentLogs, setRecentLogs] = useState<any[]>([]);
  const [deviceStatus, setDeviceStatus] = useState({
    esp32: "offline",
    backend: "online",
    camera: "online"
  });

  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [registerForm, setRegisterForm] = useState({ name: "", email: "", file: null as File | null });
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!registerForm.name || !registerForm.email || !registerForm.file) {
      alert("Please fill all fields and select a photo.");
      return;
    }
    
    setIsSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("name", registerForm.name);
      formData.append("email", registerForm.email);
      formData.append("photo", registerForm.file);
      
      const res = await fetch("http://localhost:8000/api/users/register", {
        method: "POST",
        body: formData,
      });
      
      const data = await res.json();
      if (data.status === "success") {
        alert("Face registered successfully!");
        setIsRegisterModalOpen(false);
        setRegisterForm({ name: "", email: "", file: null });
      } else {
        alert("Registration failed: " + data.message);
      }
    } catch (err) {
      console.error(err);
      alert("An error occurred during registration.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const fetchDashboardData = async () => {
    try {
      const usersRes = await fetch("http://localhost:8000/api/users");
      const usersData = await usersRes.json();
      setUsersCount(usersData.length);
      
      const logsRes = await fetch("http://localhost:8000/api/logs?limit=10");
      const logsData = await logsRes.json();
      setRecentLogs(logsData);
    } catch (e) {
      console.error("Failed to fetch dashboard data", e);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleManualControl = async (action: 'open' | 'close') => {
    try {
      await fetch(`http://localhost:8000/api/gate/${action}?source=manual`, { method: "POST" });
      setGateStatus(action.toUpperCase());
      setTimeout(fetchDashboardData, 500);
    } catch (e) {
      console.error(`Failed to ${action} gate`, e);
    }
  };

  const getPhotoUrl = (photo: string) => photo.startsWith("http") ? photo : `http://localhost:8000${photo}`;

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-50 p-6 md:p-12 font-sans selection:bg-indigo-500/30">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Header */}
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-neutral-800">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">
              <ShieldCheck className="w-8 h-8 text-indigo-500" />
              Smart Gate Access
            </h1>
            <p className="text-neutral-400 mt-1">AI-powered facial recognition system</p>
          </div>
          <div className="mt-4 md:mt-0 flex gap-4">
            <div className={`px-4 py-1.5 rounded-full text-sm font-medium flex items-center gap-2 border ${
              gateStatus === "OPEN" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-neutral-800 text-neutral-300 border-neutral-700"
            }`}>
              <div className={`w-2 h-2 rounded-full ${gateStatus === "OPEN" ? "bg-emerald-400 animate-pulse" : "bg-neutral-400"}`} />
              Gate {gateStatus}
            </div>
          </div>
        </header>

        {/* Two-Column Layout: Left = Camera + Logs (each full height), Right = 3 stacked cards */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
          
          {/* LEFT COLUMN: Camera + Logs (stacked vertically) */}
          <div className="flex flex-col gap-6 min-h-0">
            
            {/* Live Camera Stream - Fixed 16:9 Landscape */}
            <div className="rounded-3xl bg-neutral-900 border border-neutral-800 overflow-hidden relative group shadow-xl aspect-video max-h-[520px] flex-shrink-0">
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent z-10" />
              <div className="absolute top-4 left-4 z-20 flex gap-2">
                <div className="bg-black/50 backdrop-blur-md px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 border border-white/10">
                  <div className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse" />
                  LIVE
                </div>
              </div>
              
              <div className="w-full h-full relative">
                 {deviceStatus.camera === "online" ? (
                   <img 
                     src="http://localhost:8000/api/video_feed" 
                     alt="Live Camera Feed" 
                     className="w-full h-full object-cover"
                     onError={() => setDeviceStatus(prev => ({ ...prev, camera: "offline" }))}
                   />
                 ) : (
                   <div className="w-full h-full flex flex-col items-center justify-center bg-neutral-950">
                     <VideoOff className="w-16 h-16 text-neutral-800 mb-4" />
                     <p className="text-neutral-500 font-medium">Camera Feed Offline</p>
                   </div>
                 )}
              </div>
            </div>

            {/* Access Logs - Fixed height with scroll */}
            <div className="rounded-3xl bg-neutral-900 border border-neutral-800 p-6 shadow-lg overflow-hidden flex flex-col max-h-[360px] flex-1 min-h-0">
              <h3 className="text-neutral-400 text-sm font-semibold uppercase tracking-wider mb-4 flex justify-between items-center flex-shrink-0">
                <span>Recent Activity</span>
                <span className="text-xs text-indigo-400 cursor-pointer hover:text-indigo-300">View All</span>
              </h3>
              
              <div className="overflow-y-auto pr-2 custom-scrollbar flex-1 min-h-0">
                <div className="space-y-3">
                  {recentLogs.map((log, i) => (
                    <div key={i} className="flex items-center justify-between p-3 rounded-2xl bg-neutral-950/50 border border-neutral-800/50 hover:bg-neutral-800/50 transition-colors">
                      <div className="flex items-center gap-4">
                        <img src={getPhotoUrl(log.photo)} alt="face" className="w-10 h-10 rounded-full border border-neutral-700 object-cover" />
                        <div>
                          <div className="font-medium text-sm text-neutral-200">{log.name}</div>
                          <div className="text-xs text-neutral-500">{log.method}</div>
                        </div>
                      </div>
                      <div className="text-right flex flex-col items-end">
                        <div className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                          log.status === "Success" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                        }`}>
                          {log.status}
                        </div>
                        <div className="text-xs text-neutral-500 mt-1">
                          {log.created_at ? new Date(log.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Just now"}
                        </div>
                      </div>
                    </div>
                  ))}
                  {recentLogs.length === 0 && (
                    <div className="text-center text-sm text-neutral-500 py-4">No recent activity</div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN: 3 Stacked Cards */}
          <div className="flex flex-col gap-6">
            
            {/* Device Health */}
            <div className="rounded-3xl bg-neutral-900 border border-neutral-800 p-6 flex flex-col justify-between shadow-lg hover:border-neutral-700 transition-colors">
              <div>
                <h3 className="text-neutral-400 text-sm font-semibold uppercase tracking-wider mb-4 flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  System Health
                </h3>
                <div className="space-y-4 mt-6">
                  
                  <div className="flex justify-between items-center">
                    <span className="text-sm">ESP32 Controller</span>
                    {deviceStatus.esp32 === "online" ? <Wifi className="w-4 h-4 text-emerald-400" /> : <WifiOff className="w-4 h-4 text-red-400" />}
                  </div>
                  
                  <div className="flex justify-between items-center">
                    <span className="text-sm">AI Backend</span>
                    {deviceStatus.backend === "online" ? <Wifi className="w-4 h-4 text-emerald-400" /> : <WifiOff className="w-4 h-4 text-red-400" />}
                  </div>

                  <div className="flex justify-between items-center">
                    <span className="text-sm">Camera Stream</span>
                    {deviceStatus.camera === "online" ? <Wifi className="w-4 h-4 text-emerald-400" /> : <WifiOff className="w-4 h-4 text-red-400" />}
                  </div>

                </div>
              </div>
            </div>

            {/* User Management Shortcut */}
            <div 
              onClick={() => setIsRegisterModalOpen(true)}
              className="rounded-3xl bg-gradient-to-br from-indigo-600/20 to-purple-900/20 border border-indigo-500/20 p-6 flex flex-col justify-between shadow-lg hover:border-indigo-500/40 transition-colors cursor-pointer group"
            >
              <h3 className="text-indigo-300 text-sm font-semibold uppercase tracking-wider mb-2 flex items-center gap-2">
                <Users className="w-4 h-4" />
                Users
              </h3>
              <div className="mt-4">
                <div className="text-4xl font-bold text-white group-hover:scale-105 transition-transform origin-left">{usersCount}</div>
                <div className="text-indigo-200/60 text-sm mt-1">Registered Faces</div>
              </div>
              <div className="mt-6 text-sm text-indigo-400 font-medium flex items-center gap-1 group-hover:translate-x-1 transition-transform">
                Manage database &rarr;
              </div>
            </div>

            {/* Quick Actions */}
            <div className="rounded-3xl bg-neutral-900 border border-neutral-800 p-6 flex flex-col shadow-lg">
               <h3 className="text-neutral-400 text-sm font-semibold uppercase tracking-wider mb-4">Manual Control</h3>
               <div className="flex-1 flex flex-col gap-3 justify-center">
                  <button onClick={() => handleManualControl('open')} className="w-full py-4 rounded-2xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition-colors shadow-[0_0_15px_rgba(5,150,105,0.2)]">
                    Open Gate
                  </button>
                  <button onClick={() => handleManualControl('close')} className="w-full py-4 rounded-2xl bg-neutral-800 hover:bg-neutral-700 text-white font-semibold transition-colors">
                    Close Gate
                  </button>
               </div>
            </div>
          </div>
        </div>
      </div>

      {/* Registration Modal */}
      {isRegisterModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-neutral-900 border border-neutral-800 rounded-3xl p-6 w-full max-w-md shadow-2xl relative">
            <button 
              onClick={() => setIsRegisterModalOpen(false)}
              className="absolute top-4 right-4 text-neutral-400 hover:text-white text-xl leading-none"
            >
              &times;
            </button>
            <h2 className="text-xl font-bold text-white mb-6">Register New Face</h2>
            
            <form onSubmit={handleRegisterSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-1">Full Name</label>
                <input 
                  type="text" 
                  value={registerForm.name}
                  onChange={e => setRegisterForm({...registerForm, name: e.target.value})}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-indigo-500"
                  placeholder="e.g. John Doe"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-1">Email</label>
                <input 
                  type="email" 
                  value={registerForm.email}
                  onChange={e => setRegisterForm({...registerForm, email: e.target.value})}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-indigo-500"
                  placeholder="e.g. john@example.com"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-1">Face Photo</label>
                <input 
                  type="file" 
                  accept="image/*"
                  onChange={e => setRegisterForm({...registerForm, file: e.target.files ? e.target.files[0] : null})}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2 text-white file:mr-4 file:py-1 file:px-3 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-500/10 file:text-indigo-400 hover:file:bg-indigo-500/20"
                />
              </div>
              
              <button 
                type="submit" 
                disabled={isSubmitting}
                className="w-full py-3 mt-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-colors disabled:opacity-50"
              >
                {isSubmitting ? "Registering..." : "Submit Registration"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
