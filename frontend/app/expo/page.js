import { redirect } from 'next/navigation';

export default function ExpoPage() {
  redirect('/kitchen?station=expo&view=ready');
}
