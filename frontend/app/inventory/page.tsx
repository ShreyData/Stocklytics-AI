'use client';

import { useEffect, useState, useCallback } from 'react';
import { AppLayout } from '@/components/app-layout';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { Product, ProductCreateRequest, ProductUpdateRequest, StockAdjustmentRequest } from '@/lib/types';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Plus, Pencil, PackagePlus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/errors';

// ---------------------------------------------------------------------------
// Add Product Dialog
// ---------------------------------------------------------------------------

function AddProductDialog({
  open, onOpenChange, storeId, onSuccess,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  storeId: string;
  onSuccess: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    name: '', category: '', price: '', quantity: '', reorder_threshold: '', expiry_date: '',
  });

  const handleSubmit = async () => {
    if (!form.name || !form.category || !form.price || !form.quantity || !form.reorder_threshold) {
      toast.error('Please fill in all required fields');
      return;
    }
    setSubmitting(true);
    try {
      const payload: ProductCreateRequest = {
        store_id: storeId,
        name: form.name,
        category: form.category,
        price: parseFloat(form.price),
        quantity: parseInt(form.quantity, 10),
        reorder_threshold: parseInt(form.reorder_threshold, 10),
        expiry_date: form.expiry_date ? new Date(form.expiry_date).toISOString() : undefined,
      };
      await apiService.createProduct(payload);
      toast.success(`Product "${form.name}" created successfully`);
      setForm({ name: '', category: '', price: '', quantity: '', reorder_threshold: '', expiry_date: '' });
      onOpenChange(false);
      onSuccess();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Failed to create product'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Product</DialogTitle>
          <DialogDescription>Add a new product to your inventory.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Rice 5kg" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">Category *</Label>
              <Input id="category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Groceries" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="price">Price *</Label>
              <Input id="price" type="number" min="0" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="320.00" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="quantity">Quantity *</Label>
              <Input id="quantity" type="number" min="0" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} placeholder="25" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reorder">Reorder At *</Label>
              <Input id="reorder" type="number" min="0" value={form.reorder_threshold} onChange={(e) => setForm({ ...form, reorder_threshold: e.target.value })} placeholder="8" />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="expiry">Expiry Date</Label>
            <Input id="expiry" type="date" value={form.expiry_date} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Creating...' : 'Create Product'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Edit Product Dialog
// ---------------------------------------------------------------------------

function EditProductDialog({
  open, onOpenChange, product, storeId, onSuccess,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  product: Product | null;
  storeId: string;
  onSuccess: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ name: '', category: '', price: '', reorder_threshold: '', expiry_date: '' });

  useEffect(() => {
    if (product) {
      setForm({
        name: product.name,
        category: product.category,
        price: product.price.toString(),
        reorder_threshold: product.reorder_threshold.toString(),
        expiry_date: product.expiry_date ? product.expiry_date.split('T')[0] : '',
      });
    }
  }, [product]);

  const handleSubmit = async () => {
    if (!product) return;
    setSubmitting(true);
    try {
      const payload: ProductUpdateRequest = {
        store_id: storeId,
        ...(form.name !== product.name && { name: form.name }),
        ...(form.category !== product.category && { category: form.category }),
        ...(parseFloat(form.price) !== product.price && { price: parseFloat(form.price) }),
        ...(parseInt(form.reorder_threshold) !== product.reorder_threshold && {
          reorder_threshold: parseInt(form.reorder_threshold, 10),
        }),
        ...(form.expiry_date && { expiry_date: new Date(form.expiry_date).toISOString() }),
      };
      await apiService.updateProduct(product.product_id, payload);
      toast.success(`Product "${form.name}" updated`);
      onOpenChange(false);
      onSuccess();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Failed to update product'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Product</DialogTitle>
          <DialogDescription>Update product details. Only changed fields are sent.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Name</Label>
              <Input id="edit-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-category">Category</Label>
              <Input id="edit-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-price">Price</Label>
              <Input id="edit-price" type="number" min="0" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-reorder">Reorder Threshold</Label>
              <Input id="edit-reorder" type="number" min="0" value={form.reorder_threshold} onChange={(e) => setForm({ ...form, reorder_threshold: e.target.value })} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-expiry">Expiry Date</Label>
            <Input id="edit-expiry" type="date" value={form.expiry_date} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Saving...' : 'Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Stock Adjustment Dialog
// ---------------------------------------------------------------------------

function StockAdjustDialog({
  open, onOpenChange, product, storeId, onSuccess,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  product: Product | null;
  storeId: string;
  onSuccess: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ adjustment_type: 'ADD' as StockAdjustmentRequest['adjustment_type'], quantity_delta: '', reason: '' });

  const handleSubmit = async () => {
    if (!product || !form.quantity_delta || !form.reason) {
      toast.error('Please fill in all fields');
      return;
    }
    setSubmitting(true);
    try {
      const payload: StockAdjustmentRequest = {
        store_id: storeId,
        adjustment_type: form.adjustment_type,
        quantity_delta: parseInt(form.quantity_delta, 10),
        reason: form.reason,
      };
      await apiService.adjustStock(product.product_id, payload);
      toast.success(`Stock adjusted for "${product.name}"`);
      setForm({ adjustment_type: 'ADD', quantity_delta: '', reason: '' });
      onOpenChange(false);
      onSuccess();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Failed to adjust stock'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Adjust Stock</DialogTitle>
          <DialogDescription>
            {product ? `Adjust stock for ${product.name} (current: ${product.quantity_on_hand})` : 'Adjust stock'}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="space-y-2">
            <Label>Adjustment Type</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.adjustment_type}
              onChange={(event) =>
                setForm({
                  ...form,
                  adjustment_type: event.target.value as StockAdjustmentRequest['adjustment_type'],
                })
              }
            >
              <option value="ADD">Add Stock</option>
              <option value="REMOVE">Remove Stock</option>
              <option value="MANUAL_CORRECTION">Manual Correction</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="adj-qty">Quantity</Label>
            <Input id="adj-qty" type="number" min="1" value={form.quantity_delta} onChange={(e) => setForm({ ...form, quantity_delta: e.target.value })} placeholder="10" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="adj-reason">Reason *</Label>
            <Input id="adj-reason" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="New shipment arrived" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Adjusting...' : 'Apply Adjustment'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Inventory Page
// ---------------------------------------------------------------------------

export default function Inventory() {
  const { storeId } = useAuth();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [showLowStockOnly, setShowLowStockOnly] = useState(false);

  // Dialog state
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);

  const fetchProducts = useCallback(async () => {
    if (!storeId) return;
    try {
      setLoading(true);
      const res = await apiService.getProducts(storeId);
      setProducts(res.items);
    } catch (error) {
      console.error('Failed to fetch products', error);
      toast.error(getErrorMessage(error, 'Failed to load inventory'));
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    setShowLowStockOnly(params.get('low_stock_only') === 'true');
  }, []);

  const handleEdit = (product: Product) => {
    setSelectedProduct(product);
    setEditOpen(true);
  };

  const handleAdjust = (product: Product) => {
    setSelectedProduct(product);
    setAdjustOpen(true);
  };

  const visibleProducts = showLowStockOnly
    ? products.filter((product) => product.quantity_on_hand <= product.reorder_threshold)
    : products;

  return (
    <AppLayout>
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Inventory</h1>
            {showLowStockOnly ? (
              <p className="mt-1 text-sm text-muted-foreground">Showing only low stock products from the dashboard quick link.</p>
            ) : null}
          </div>
          <Button onClick={() => setAddOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Add Product
          </Button>
        </div>

        <div className="border rounded-md">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Quantity</TableHead>
                <TableHead>Expiry Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                    Loading inventory...
                  </TableCell>
                </TableRow>
              ) : visibleProducts.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                    {showLowStockOnly
                      ? 'No low stock products right now.'
                      : 'No products found. Click "Add Product" to get started.'}
                  </TableCell>
                </TableRow>
              ) : (
                visibleProducts.map((product) => {
                  const isLowStock = product.quantity_on_hand <= product.reorder_threshold;
                  return (
                    <TableRow
                      key={product.product_id}
                      className={cn(isLowStock && 'glow-red bg-red-500/5')}
                    >
                      <TableCell className="font-medium">{product.name}</TableCell>
                      <TableCell className="text-muted-foreground">{product.category}</TableCell>
                      <TableCell>₹{product.price.toFixed(2)}</TableCell>
                      <TableCell>
                        <span className={cn(isLowStock && 'text-red-500 font-bold')}>
                          {product.quantity_on_hand}
                        </span>
                      </TableCell>
                      <TableCell>
                        {product.expiry_date
                          ? format(new Date(product.expiry_date), 'MMM d, yyyy')
                          : '—'}
                      </TableCell>
                      <TableCell>
                        {product.expiry_status === 'OK' && <Badge variant="outline">OK</Badge>}
                        {product.expiry_status === 'EXPIRING_SOON' && (
                          <Badge variant="secondary" className="bg-yellow-500/20 text-yellow-500 hover:bg-yellow-500/30">
                            Expiring Soon
                          </Badge>
                        )}
                        {product.expiry_status === 'EXPIRED' && (
                          <Badge variant="destructive">Expired</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleEdit(product)} title="Edit product">
                            <Pencil className="w-4 h-4" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleAdjust(product)} title="Adjust stock">
                            <PackagePlus className="w-4 h-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Dialogs */}
      <AddProductDialog open={addOpen} onOpenChange={setAddOpen} storeId={storeId} onSuccess={fetchProducts} />
      <EditProductDialog open={editOpen} onOpenChange={setEditOpen} product={selectedProduct} storeId={storeId} onSuccess={fetchProducts} />
      <StockAdjustDialog open={adjustOpen} onOpenChange={setAdjustOpen} product={selectedProduct} storeId={storeId} onSuccess={fetchProducts} />
    </AppLayout>
  );
}
