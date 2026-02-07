import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AccountProvider } from './contexts/AccountContext';
import { Layout } from './components/Layout';
import { DashboardPage } from './pages/DashboardPage';
import { HealthPage } from './pages/HealthPage';
import { BacktestPage } from './pages/BacktestPage';
import { StoragePage } from './pages/StoragePage';
import { AlertsPage } from './pages/AlertsPage';
import { AuditPage } from './pages/AuditPage';
import { SystemPage } from './pages/SystemPage';
import { OptionsExpiringPage } from './pages/OptionsExpiringPage';
import { GreeksPage } from './pages/GreeksPage';
import { DerivativesPage } from './pages/DerivativesPage';
import { AgentsPage } from './pages/AgentsPage';

function App() {
  return (
    <AccountProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/storage" element={<StoragePage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/options/expiring" element={<OptionsExpiringPage />} />
            <Route path="/derivatives" element={<DerivativesPage />} />
            <Route path="/greeks" element={<GreeksPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/system" element={<SystemPage />} />
            <Route path="/agents" element={<AgentsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AccountProvider>
  );
}

export default App;
