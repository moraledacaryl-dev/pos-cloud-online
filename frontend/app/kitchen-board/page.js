import { redirect } from 'next/navigation';

export default function KitchenBoardPage() {
  redirect('/kitchen?view=active');
}
