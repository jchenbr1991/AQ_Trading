import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { DashboardPage } from './pages/DashboardPage';
import { HealthPage } from './pages/HealthPage';

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
          </div>
        </div>
      </div>
    </nav>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-100">
        <Navigation />
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/health" element={<HealthPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
