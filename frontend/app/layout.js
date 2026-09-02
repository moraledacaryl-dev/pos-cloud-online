import './globals.css';
import './mobile-accessibility.css';
import './pass12-runtime.css';
import './pass13-accessibility.css';
import { connection } from 'next/server';
import AppShell from '../components/AppShell';
import { CurrentUserProvider } from '../lib/useCurrentUser';

export const metadata = { title: 'POS Cloud' };

export default async function RootLayout({ children }) {
  await connection();

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
