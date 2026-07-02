import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout.tsx';
import { DashboardPage } from './pages/DashboardPage.tsx';
import { ChatPage } from './pages/ChatPage.tsx';
import { SessionsPage } from './pages/SessionsPage.tsx';
import { SettingsPage } from './pages/SettingsPage.tsx';
import { NotFoundPage } from './pages/NotFoundPage.tsx';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="chat/:sessionId" element={<ChatPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
