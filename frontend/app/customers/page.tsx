'use client';

import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { Plus } from 'lucide-react';
import { AppLayout } from '@/components/app-layout';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useAuth } from '@/components/auth-provider';
import { apiService } from '@/lib/api-service';
import { Customer, CustomerPurchaseHistoryItem } from '@/lib/types';
import { getErrorMessage } from '@/lib/errors';
import { toast } from 'sonner';

export default function Customers() {
  const { storeId } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [purchaseHistory, setPurchaseHistory] = useState<CustomerPurchaseHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '' });

  useEffect(() => {
    if (!storeId) {
      return;
    }

    async function loadCustomers() {
      setLoading(true);
      try {
        const res = await apiService.getCustomers();
        setCustomers(res.items || []);
        if (!selectedCustomerId && res.items.length > 0) {
          setSelectedCustomerId(res.items[0].customer_id);
        }
      } catch (error) {
        toast.error(getErrorMessage(error, 'Failed to load customers.'));
      } finally {
        setLoading(false);
      }
    }

    void loadCustomers();
  }, [storeId, selectedCustomerId]);

  useEffect(() => {
    if (!selectedCustomerId) {
      setSelectedCustomer(null);
      setPurchaseHistory([]);
      return;
    }

    async function loadCustomerDetails() {
      setDetailsLoading(true);
      try {
        const [detailRes, historyRes] = await Promise.all([
          apiService.getCustomer(selectedCustomerId),
          apiService.getCustomerPurchaseHistory(selectedCustomerId),
        ]);
        setSelectedCustomer(detailRes.customer);
        setPurchaseHistory(historyRes.transactions);
      } catch (error) {
        toast.error(getErrorMessage(error, 'Failed to load customer details.'));
      } finally {
        setDetailsLoading(false);
      }
    }

    void loadCustomerDetails();
  }, [selectedCustomerId]);

  async function handleCreateCustomer() {
    if (!storeId) {
      return;
    }
    if (!form.name.trim() || !form.phone.trim()) {
      toast.error('Name and phone are required.');
      return;
    }

    setSaving(true);
    try {
      const created = await apiService.createCustomer({
        store_id: storeId,
        name: form.name.trim(),
        phone: form.phone.trim(),
      });
      toast.success('Customer created.');
      setCustomers((prev) => [created.customer, ...prev]);
      setSelectedCustomerId(created.customer.customer_id);
      setForm({ name: '', phone: '' });
      setOpen(false);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to create customer.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppLayout>
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Customers</h1>
            <p className="text-sm text-muted-foreground">
              View customer profiles and billing-driven purchase history from completed transactions.
            </p>
          </div>
          <Button onClick={() => setOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Add Customer
          </Button>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <Card>
            <CardHeader>
              <CardTitle>Customer Directory</CardTitle>
              <CardDescription>Select a customer to inspect profile details and purchase history.</CardDescription>
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
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                        Loading customers...
                      </TableCell>
                    </TableRow>
                  ) : customers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                        No customers found.
                      </TableCell>
                    </TableRow>
                  ) : (
                    customers.map((customer) => (
                      <TableRow
                        key={customer.customer_id}
                        className={customer.customer_id === selectedCustomerId ? 'bg-muted/50' : 'cursor-pointer'}
                        onClick={() => setSelectedCustomerId(customer.customer_id)}
                      >
                        <TableCell className="font-medium">{customer.name}</TableCell>
                        <TableCell>{customer.phone}</TableCell>
                        <TableCell>₹{customer.total_spend.toFixed(2)}</TableCell>
                        <TableCell>{customer.visit_count}</TableCell>
                        <TableCell>
                          {customer.last_purchase_at
                            ? format(new Date(customer.last_purchase_at), 'PPp')
                            : '—'}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Customer Detail</CardTitle>
              <CardDescription>Uses the live customer profile and purchase-history API contracts.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {detailsLoading ? (
                <div className="text-sm text-muted-foreground">Loading customer detail...</div>
              ) : !selectedCustomer ? (
                <div className="text-sm text-muted-foreground">Select a customer to inspect details.</div>
              ) : (
                <>
                  <div className="space-y-2">
                    <div>
                      <p className="text-xs uppercase tracking-widest text-muted-foreground">Name</p>
                      <p className="font-medium">{selectedCustomer.name}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-widest text-muted-foreground">Phone</p>
                      <p>{selectedCustomer.phone}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs uppercase tracking-widest text-muted-foreground">Total Spend</p>
                        <p className="font-semibold">₹{selectedCustomer.total_spend.toFixed(2)}</p>
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-widest text-muted-foreground">Visits</p>
                        <p className="font-semibold">{selectedCustomer.visit_count}</p>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <p className="text-xs uppercase tracking-widest text-muted-foreground">Purchase History</p>
                      <p className="text-sm text-muted-foreground">
                        Completed billing transactions linked to this customer.
                      </p>
                    </div>
                    <div className="space-y-2">
                      {purchaseHistory.length === 0 ? (
                        <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                          No linked purchases yet.
                        </div>
                      ) : (
                        purchaseHistory.map((transaction) => (
                          <div
                            key={transaction.transaction_id}
                            className="rounded-md border border-border bg-muted/20 p-3"
                          >
                            <div className="flex items-center justify-between gap-4">
                              <span className="font-medium">{transaction.transaction_id}</span>
                              <span className="font-semibold">₹{transaction.total_amount.toFixed(2)}</span>
                            </div>
                            <p className="mt-1 text-sm text-muted-foreground">
                              {format(new Date(transaction.sale_timestamp), 'PPp')}
                            </p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Customer</DialogTitle>
            <DialogDescription>Create a customer profile for billing and analytics attribution.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="customer-name">Name</Label>
              <Input
                id="customer-name"
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="Customer name"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="customer-phone">Phone</Label>
              <Input
                id="customer-phone"
                value={form.phone}
                onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
                placeholder="+91XXXXXXXXXX"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateCustomer} disabled={saving}>
              {saving ? 'Creating...' : 'Create Customer'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
