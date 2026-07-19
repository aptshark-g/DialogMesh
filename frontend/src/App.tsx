import { lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout.tsx';
import { ChatPage } from './pages/ChatPage.tsx';
import { NotFoundPage } from './pages/NotFoundPage.tsx';
import { FloatingActionButton } from './components/FloatingActionButton.tsx';
import { ContentScriptBridge } from './components/ContentScriptBridge.tsx';

const DashboardPage = lazy(() => import('./pages/DashboardPage.tsx').then((m) => ({ default: m.DashboardPage })));
const SessionsPage = lazy(() => import('./pages/SessionsPage.tsx').then((m) => ({ default: m.SessionsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage.tsx').then((m) => ({ default: m.SettingsPage })));
const ConversationGraphPage = lazy(() => import('./pages/ConversationGraphPage.tsx').then((m) => ({ default: m.ConversationGraphPage })));
const CognitiveProfilePage = lazy(() => import('./pages/CognitiveProfilePage.tsx').then((m) => ({ default: m.CognitiveProfilePage })));
const TaskPlanningPage = lazy(() => import('./pages/TaskPlanningPage.tsx').then((m) => ({ default: m.TaskPlanningPage })));
const GatewayPage = lazy(() => import('./pages/GatewayPage.tsx').then((m) => ({ default: m.GatewayPage })));
const PipelinePage = lazy(() => import('./pages/PipelinePage.tsx').then((m) => ({ default: m.PipelinePage })));
const DeepChainPage = lazy(() => import('./pages/DeepChainPage.tsx').then((m) => ({ default: m.DeepChainPage })));
const MetaCenterPage = lazy(() => import('./pages/MetaCenterPage.tsx').then((m) => ({ default: m.MetaCenterPage })));
const BehaviorPage = lazy(() => import('./pages/BehaviorPage.tsx').then((m) => ({ default: m.BehaviorPage })));
const EngineeringPage = lazy(() => import('./pages/EngineeringPage.tsx').then((m) => ({ default: m.EngineeringPage })));

export default function App() {
  return (
    <BrowserRouter>
      <ContentScriptBridge />
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="graph" element={<ConversationGraphPage />} />
          <Route path="profile" element={<CognitiveProfilePage />} />
          <Route path="tasks" element={<TaskPlanningPage />} />
          <Route path="gateway" element={<GatewayPage />} />
          <Route path="pipeline" element={<PipelinePage />} />
          <Route path="deepchain" element={<DeepChainPage />} />
          <Route path="meta" element={<MetaCenterPage />} />
          <Route path="behavior" element={<BehaviorPage />} />
          <Route path="engineering" element={<EngineeringPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
      <FloatingActionButton />
    </BrowserRouter>
  );
}
