'use client';

import { useState, useEffect } from 'react';
import { AppLayout } from '@/components/app-layout';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { Customer, Product } from '@/lib/types';
import { v4 as uuidv4 } from 'uuid';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import { Plus, Minus, Trash2, ShoppingCart } from 'lucide-react';
import { getBillingFailureMessage, getErrorMessage } from '@/lib/errors';

interface CartItem extends Product {
  cartQuantity: number;
}

export default function Billing() {
  const { storeId } = useAuth();
  const [products, setProducts] = useState<Product[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<'cash' | 'upi' | 'card'>('cash');
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');
  const [idempotencyKey, setIdempotencyKey] = useState(uuidv4());

  useEffect(() => {
    if (!storeId) return;

    const fetchData = async () => {
      const [productsRes, customersRes] = await Promise.allSettled([
        apiService.getProducts(storeId),
        apiService.getCustomers(),
      ]);

      if (productsRes.status === 'fulfilled') {
        setProducts(productsRes.value.items);
      } else {
        setProducts([]);
        toast.error(
          getErrorMessage(productsRes.reason, 'Failed to load products for billing.')
        );
      }

      if (customersRes.status === 'fulfilled') {
        setCustomers(customersRes.value.items);
      } else {
        setCustomers([]);
        toast.error(
          getErrorMessage(customersRes.reason, 'Failed to load customers for billing.')
        );
      }
    };
    fetchData();
  }, [storeId]);

  const addToCart = (product: Product) => {
    setCart((prev) => {
      const existing = prev.find((item) => item.product_id === product.product_id);
      if (existing) {
        if (existing.cartQuantity >= product.quantity_on_hand) {
          toast.warning('Not enough stock available');
          return prev;
        }
        return prev.map((item) =>
          item.product_id === product.product_id
            ? { ...item, cartQuantity: item.cartQuantity + 1 }
            : item
        );
      }
      if (product.quantity_on_hand <= 0) {
        toast.warning('Out of stock');
        return prev;
      }
      return [...prev, { ...product, cartQuantity: 1 }];
    });
  };

  const updateQuantity = (productId: string, delta: number) => {
    setCart((prev) =>
      prev.map((item) => {
        if (item.product_id === productId) {
          const newQuantity = item.cartQuantity + delta;
          if (newQuantity > item.quantity_on_hand) {
            toast.warning('Not enough stock available');
            return item;
          }
          return { ...item, cartQuantity: Math.max(1, newQuantity) };
        }
        return item;
      })
    );
  };

  const removeFromCart = (productId: string) => {
    setCart((prev) => prev.filter((item) => item.product_id !== productId));
  };

  const totalAmount = cart.reduce((acc, item) => acc + item.price * item.cartQuantity, 0);

  const handleCheckout = async () => {
    if (cart.length === 0 || !storeId) return;
    setIsSubmitting(true);

    try {
      const payload = {
        store_id: storeId,
        idempotency_key: idempotencyKey,
        payment_method: paymentMethod,
        ...(selectedCustomerId ? { customer_id: selectedCustomerId } : {}),
        items: cart.map((item) => ({
          product_id: item.product_id,
          quantity: item.cartQuantity,
        })),
      };

      const res = await apiService.createTransaction(payload);
      const message = res.idempotent_replay
        ? 'This request was safely replayed using the same idempotency key.'
        : 'Transaction completed successfully.';
      toast.success(message);
      setCart([]);
      setIdempotencyKey(uuidv4());
    } catch (error) {
      toast.error(getBillingFailureMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AppLayout>
      <div className="space-y-8">
        <h1 className="text-3xl font-bold tracking-tight">Billing</h1>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium">Payment Method</label>
                <select
                  className="mt-2 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={paymentMethod}
                  onChange={(event) =>
                    setPaymentMethod(event.target.value as 'cash' | 'upi' | 'card')
                  }
                >
                  <option value="cash">Cash</option>
                  <option value="upi">UPI</option>
                  <option value="card">Card</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Customer (Optional)</label>
                <select
                  className="mt-2 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={selectedCustomerId || '__none__'}
                  onChange={(event) => {
                    const normalized = event.target.value || '__none__';
                    setSelectedCustomerId(normalized === '__none__' ? '' : normalized);
                  }}
                >
                  <option value="__none__">Walk-in customer</option>
                  {customers.map((customer) => (
                    <option key={customer.customer_id} value={customer.customer_id}>
                      {customer.name} ({customer.phone})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <h2 className="text-xl font-semibold">Products</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {products.length === 0 ? (
                <Card className="col-span-full">
                  <CardContent className="p-6 text-sm text-muted-foreground">
                    No products are available for this store yet, or the product list request failed.
                  </CardContent>
                </Card>
              ) : (
                products.map((product) => (
                  <Card
                    key={product.product_id}
                    className="cursor-pointer hover:border-primary transition-colors"
                    onClick={() => addToCart(product)}
                  >
                    <CardContent className="p-4 flex flex-col items-center justify-center text-center h-full">
                      <div className="font-medium">{product.name}</div>
                      <div className="text-muted-foreground">${product.price.toFixed(2)}</div>
                      <div className="text-xs mt-2 text-muted-foreground">
                        Stock: {product.quantity_on_hand}
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </div>

          <div>
            <Card className="sticky top-8">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShoppingCart className="w-5 h-5" />
                  Current Bill
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {cart.length === 0 ? (
                  <div className="text-center text-muted-foreground py-8">Cart is empty</div>
                ) : (
                  <div className="space-y-4">
                    {cart.map((item) => (
                      <div key={item.product_id} className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="font-medium">{item.name}</div>
                          <div className="text-sm text-muted-foreground">
                            ${item.price.toFixed(2)} x {item.cartQuantity}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => updateQuantity(item.product_id, -1)}
                          >
                            <Minus className="w-3 h-3" />
                          </Button>
                          <span className="w-4 text-center text-sm">{item.cartQuantity}</span>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => updateQuantity(item.product_id, 1)}
                          >
                            <Plus className="w-3 h-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive ml-2"
                            onClick={() => removeFromCart(item.product_id)}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                    <div className="border-t pt-4 mt-4">
                      <div className="flex items-center justify-between font-bold text-lg">
                        <span>Total</span>
                        <span>${totalAmount.toFixed(2)}</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-2">
                        Retry safety key: {idempotencyKey}
                      </p>
                    </div>
                    <Button
                      className="w-full"
                      size="lg"
                      onClick={handleCheckout}
                      disabled={isSubmitting || cart.length === 0}
                    >
                      {isSubmitting ? 'Processing...' : 'Complete Transaction'}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
