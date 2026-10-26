import { Navigate, Route, Routes } from "react-router-dom";
import { StoreProvider, useStore } from "./lib/store";
import { ToastProvider } from "./components/Toast";
import Sidebar from "./components/Sidebar";
import Assistant from "./components/Assistant";
import Home from "./pages/Home";
import Jobs from "./pages/Jobs";
import JobDetail from "./pages/JobDetail";
import Me from "./pages/Me";
import Settings from "./pages/Settings";

function Shell() {
  const { chatOpen } = useStore();
  return (
    <div className="grid h-full min-h-0" style={{ gridTemplateColumns: chatOpen ? "232px minmax(0,1fr) 400px" : "232px minmax(0,1fr) 0px", transition: "grid-template-columns .2s ease" }}>
      <Sidebar />
      <main className="min-w-0 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/me" element={<Me />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Assistant />
    </div>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <ToastProvider>
        <Shell />
      </ToastProvider>
    </StoreProvider>
  );
}
