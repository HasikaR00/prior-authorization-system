import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import Login from './pages/Login';
import Register from './pages/Register';
import InitiatorDashboard from './pages/InitiatorDashboard';
import NewRequest from './pages/NewRequest';
import RequestDetail from './pages/RequestDetail';
import InsurerQueue from './pages/InsurerQueue';
import InsurerReview from './pages/InsurerReview';
import SubmissionConfirmed from './pages/SubmissionConfirmed';

import Profile from './pages/Profile';

function ProtectedRoute({ children, allowedRole }) {
  const role = localStorage.getItem('user_role');
  if (!role) {
    return <Navigate to="/login" replace />;
  }
  if (allowedRole && role !== allowedRole) {
    return <Navigate to={role === 'insurer' ? '/queue' : '/dashboard'} replace />;
  }
  return children;
}

export default function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        
        {/* Initiator routes */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute allowedRole="initiator">
              <InitiatorDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/new-request"
          element={
            <ProtectedRoute allowedRole="initiator">
              <NewRequest />
            </ProtectedRoute>
          }
        />
        <Route
          path="/submitted"
          element={
            <ProtectedRoute allowedRole="initiator">
              <SubmissionConfirmed />
            </ProtectedRoute>
          }
        />

        {/* Shared Profile & Detail routes */}
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <Profile />
            </ProtectedRoute>
          }
        />
        <Route
          path="/requests/:id"
          element={
            <ProtectedRoute>
              <RequestDetail />
            </ProtectedRoute>
          }
        />

        {/* Insurer routes */}
        <Route
          path="/queue"
          element={
            <ProtectedRoute allowedRole="insurer">
              <InsurerQueue />
            </ProtectedRoute>
          }
        />
        <Route
          path="/review/:id"
          element={
            <ProtectedRoute allowedRole="insurer">
              <InsurerReview />
            </ProtectedRoute>
          }
        />

        {/* Default fallback */}
        <Route
          path="*"
          element={
            localStorage.getItem('user_role') === 'insurer' ? (
              <Navigate to="/queue" replace />
            ) : localStorage.getItem('user_role') === 'initiator' ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
      </Routes>
    </Router>
    </ErrorBoundary>
  );
}
