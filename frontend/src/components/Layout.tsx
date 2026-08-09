import { Suspense } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ErrorBoundary } from './ErrorBoundary';
import { AnimatePresence, motion } from 'framer-motion';
import { Sidebar } from './Sidebar.tsx';
import { Toolbar } from './Toolbar.tsx';
import { PageLoader } from './PageLoader.tsx';
import { RightDock } from './dock/RightDock';
import { CenterDock } from './dock/CenterDock';
import { MobileBottomNav } from './MobileBottomNav.tsx';
import { SidePanel } from './ui/SidePanel.tsx';
import { ConfirmDialog } from './ui/ConfirmDialog.tsx';

export function Layout() {
  const location = useLocation();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface">
      {/* Sidebar — desktop always visible, mobile overlay drawer */}
      <Sidebar />

      {/* Main area — middle + toolbar */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Toolbar
          sessionTitle="DialogMesh"
          onSearch={(query) => console.log('Search:', query)}
        />

        <div className="flex-1 flex overflow-hidden relative">
          {/* Main content */}
          <main className="flex-1 overflow-hidden relative pb-16 lg:pb-0">
            <AnimatePresence mode="wait">
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3, ease: 'easeInOut' }}
                className="h-full w-full overflow-y-auto"
              >
                <Suspense fallback={<PageLoader />}>
                  <ErrorBoundary>
                    <Outlet />
                  </ErrorBoundary>
                </Suspense>
              </motion.div>
            </AnimatePresence>
          </main>

          {/* Right Panel */}
          <SidePanel>
            <RightDock />
          </SidePanel>

          {/* Center Dock — 内容坞"中间显示"浮层（B5） */}
          <CenterDock />
        </div>
      </div>

      {/* Mobile Bottom Navigation */}
      <MobileBottomNav />

      {/* Global Popup / Confirm Dialog */}
      <ConfirmDialog />
    </div>
  );
}
