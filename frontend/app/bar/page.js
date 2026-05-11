import { redirect } from 'next/navigation';

export default function BarPage() {
  redirect('/kitchen?station=bar&view=active');
}
