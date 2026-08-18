import './globals.css';
import './mobile-accessibility.css';
import AppShell from '../components/AppShell';
import { CurrentUserProvider } from '../lib/useCurrentUser';

export const metadata = { title: 'POS Cloud' };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <CurrentUserProvider>
          <AppShell>{children}</AppShell>
        </CurrentUserProvider>
      </body>
    </html>
  );
}
