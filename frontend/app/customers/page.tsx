'use client';

import { AppLayout } from '@/components/app-layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { format } from 'date-fns';

const mockCustomers = [
  {
    customer_id: 'cust_001',
    name: 'Ravi Kumar',
    phone: '+919999999999',
    total_spend: 3140.0,
    visit_count: 9,
    last_purchase_at: '2026-04-02T10:30:00Z',
  },
  {
    customer_id: 'cust_002',
    name: 'Priya Sharma',
    phone: '+918888888888',
    total_spend: 1250.0,
    visit_count: 3,
    last_purchase_at: '2026-04-01T14:15:00Z',
  },
];

export default function Customers() {
  return (
    <AppLayout>
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold tracking-tight">Customers</h1>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Customer Directory</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Total Spend</TableHead>
                  <TableHead>Visits</TableHead>
                  <TableHead>Last Purchase</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockCustomers.map((customer) => (
                  <TableRow key={customer.customer_id}>
                    <TableCell className="font-medium">{customer.name}</TableCell>
                    <TableCell>{customer.phone}</TableCell>
                    <TableCell>${customer.total_spend.toFixed(2)}</TableCell>
                    <TableCell>{customer.visit_count}</TableCell>
                    <TableCell>{format(new Date(customer.last_purchase_at), 'PPp')}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}
