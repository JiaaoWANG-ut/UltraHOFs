import { Spin } from 'antd';
import { lazy, Suspense, type ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './auth';
import { AppLayout } from './components/AppLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import LoginPage from './pages/LoginPage';

const HomePage = lazy(() => import('./pages/HomePage'));
const DatabasePage = lazy(() => import('./pages/DatabasePage'));
const EntryPage = lazy(() => import('./pages/EntryPage'));
const EvaluatePage = lazy(() => import('./pages/EvaluatePage'));
const GeneratePage = lazy(() => import('./pages/GeneratePage'));
const PairsPage = lazy(() => import('./pages/PairsPage'));
const MoleculePage = lazy(() => import('./pages/MoleculePage'));
const BuilderPage = lazy(() => import('./pages/BuilderPage'));
const StructuresPage = lazy(() => import('./pages/StructuresPage'));
const StructurePage = lazy(() => import('./pages/StructurePage'));
const JobsPage = lazy(() => import('./pages/JobsPage'));
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const AboutPage = lazy(() => import('./pages/AboutPage'));

function Guard({ children, curator = false }: { children: ReactNode; curator?: boolean }) {
  const { user, loading, isCurator } = useAuth();
  const loc = useLocation();
  if (loading) return <Spin style={{ margin: '30vh auto', display: 'block' }} />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (curator && !isCurator) return <Navigate to="/" replace />;
  return (
    <AppLayout>
      <ErrorBoundary resetKey={loc.pathname + loc.search}>
        <Suspense fallback={<Spin style={{ margin: '20vh auto', display: 'block' }} />}>{children}</Suspense>
      </ErrorBoundary>
    </AppLayout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Guard><HomePage /></Guard>} />
      <Route path="/database" element={<Guard><DatabasePage /></Guard>} />
      <Route path="/database/:id" element={<Guard><EntryPage /></Guard>} />
      <Route path="/design/evaluate" element={<Guard><EvaluatePage /></Guard>} />
      <Route path="/design/generate" element={<Guard><GeneratePage /></Guard>} />
      <Route path="/design/pairs" element={<Guard><PairsPage /></Guard>} />
      <Route path="/molecules/:id" element={<Guard><MoleculePage /></Guard>} />
      <Route path="/builder" element={<Guard><BuilderPage /></Guard>} />
      <Route path="/structures" element={<Guard><StructuresPage /></Guard>} />
      <Route path="/structures/:id" element={<Guard><StructurePage /></Guard>} />
      <Route path="/jobs" element={<Guard><JobsPage /></Guard>} />
      <Route path="/projects" element={<Guard><ProjectsPage /></Guard>} />
      <Route path="/projects/:id" element={<Guard><ProjectsPage /></Guard>} />
      <Route path="/admin" element={<Guard curator><AdminPage /></Guard>} />
      <Route path="/about" element={<Guard><AboutPage /></Guard>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
