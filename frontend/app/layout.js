import './globals.css';
import Sidebar from '../components/Sidebar';
import Header from '../components/Header';
import RouteGuard from '../components/RouteGuard';
import { CurrentUserProvider } from '../lib/useCurrentUser';

export const metadata = { title: 'POS Cloud' };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <CurrentUserProvider>
          <div className="app-shell">
            <Sidebar />
            <div className="main-shell">
              <Header />
              <main className="main">
                <RouteGuard>{children}</RouteGuard>
              </main>
            </div>
          </div>
        </CurrentUserProvider>
      </body>
    </html>
  );
}
