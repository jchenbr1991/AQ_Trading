import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { AccountProvider } from './contexts/AccountContext';
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

function Navigation() {
  return (
    <nav className="bg-gray-800">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-12">
          <div className="flex items-center space-x-4">
            <Link to="/" className="text-white font-medium hover:text-gray-300">
              Dashboard
            </Link>
            <Link to="/health" className="text-gray-300 hover:text-white">
              Health
            </Link>
            <Link to="/backtest" className="text-gray-300 hover:text-white">
              Backtest
            </Link>
            <Link to="/storage" className="text-gray-300 hover:text-white">
              Storage
            </Link>
            <Link to="/alerts" className="text-gray-300 hover:text-white">
              Alerts
            </Link>
            <Link to="/options/expiring" className="text-gray-300 hover:text-white">
              Options
            </Link>
            <Link to="/derivatives" className="text-gray-300 hover:text-white">
              Derivatives
            </Link>
            <Link to="/greeks" className="text-gray-300 hover:text-white">
              Greeks
            </Link>
            <Link to="/audit" className="text-gray-300 hover:text-white">
              Audit
            </Link>
            <Link to="/system" className="text-gray-300 hover:text-white">
              System
            </Link>
            <Link to="/agents" className="text-gray-300 hover:text-white">
              Agents
            </Link>
          </div>
        </div>
      </div>
    </nav>
  );
}

function App() {
  return (
    <AccountProvider>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-100">
          <Navigation />
          <Routes>
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
          </Routes>
        </div>
      </BrowserRouter>
    </AccountProvider>
  );
}

export default App;
