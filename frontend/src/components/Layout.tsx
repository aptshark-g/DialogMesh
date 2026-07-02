import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar.tsx';

export function Layout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface-main">
      <Sidebar />
      <main className="flex-1 overflow-hidden flex flex-col">
        <div className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
