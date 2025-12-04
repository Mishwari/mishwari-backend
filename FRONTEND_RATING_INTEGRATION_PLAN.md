# Frontend Rating System Integration Plan

## Overview
This document outlines the frontend changes required in both `passenger-web` and `driver-web` applications to integrate with the new backend rating system.

---

## Phase 1: Type System Updates

### 1.1 Update Shared Types Package

**File**: `packages/types/src/operator.ts`

```typescript
export const OperatorSchema = z.object({
    id: z.number(),
    name: z.string(),
    is_verified: z.boolean().optional(),
    avg_rating: z.number().default(0),
    total_reviews: z.number().default(0),
})

export type Operator = z.infer<typeof OperatorSchema>
```

### 1.2 Update Bus Types

**File**: `packages/types/src/bus.ts`

```typescript
export const BusSchema = z.object({
    id: z.number(),
    capacity: z.number(),
    bus_number: z.string(),
    bus_type: z.string(),
    amenities: z.any(),
    is_verified: z.boolean(),
    verification_documents: z.any().nullable(),
    // New rating fields
    avg_rating: z.number().default(0),
    total_reviews: z.number().default(0),
    // New amenity flags
    has_wifi: z.boolean().default(false),
    has_ac: z.boolean().default(true),
    has_usb_charging: z.boolean().default(false),
})

export type Bus = z.infer<typeof BusSchema>
```

### 1.3 Update Driver Types

**File**: `packages/types/src/driver.ts`

```typescript
export const DriverSchema = z.object({
    id: z.number(),
    driver_name: z.string(),
    mobile_number: z.string().optional(),
    email: z.string().email().optional(),
    national_id: z.string().nullable().optional(),
    driver_license: z.string().nullable().optional(),
    driver_rating: z.string(),
    total_reviews: z.number().default(0),
    operator: OperatorSchema.nullable(),
    buses: z.array(z.any()).optional(),
    is_verified: z.boolean(),
    verification_documents: z.any().optional(),
})

export type Driver = z.infer<typeof DriverSchema>
```

### 1.4 Create Review Types

**File**: `packages/types/src/review.ts` (NEW)

```typescript
import { z } from "zod";

export const ReviewSchema = z.object({
    id: z.number(),
    booking: z.number(),
    overall_rating: z.number().min(1).max(5),
    bus_condition_rating: z.number().min(1).max(5),
    driver_rating: z.number().min(1).max(5),
    comment: z.string().optional(),
    created_at: z.string(),
})

export type Review = z.infer<typeof ReviewSchema>

export interface CreateReviewPayload {
    booking: number;
    overall_rating: number;
    bus_condition_rating: number;
    driver_rating: number;
    comment?: string;
}
```

### 1.5 Update Booking Types

**File**: `packages/types/src/booking.ts`

```typescript
import { ReviewSchema } from './review'

export const BookingSchema = z.object({ 
    id: z.number(),
    user: UserDetailsSchema,
    status: z.enum(['completed', 'cancelled', 'active','pending']),
    trip: z.any(),
    from_stop: z.object({
        id: z.number(),
        city: z.object({ id: z.number(), name: z.string() }),
        sequence: z.number(),
        price_from_start: z.number(),
    }).optional(),
    to_stop: z.object({
        id: z.number(),
        city: z.object({ id: z.number(), name: z.string() }),
        sequence: z.number(),
        price_from_start: z.number(),
    }).optional(),
    passengers: z.array(PassengerSchema),
    contact_name: z.string().optional(),
    contact_phone: z.string().optional(),
    contact_email: z.string().optional(),
    is_paid: z.boolean(),
    payment_method: z.enum(['cash', 'wallet', 'stripe']),
    booking_time: z.string(),
    total_fare: z.number().optional(),
    review: ReviewSchema.optional(), // NEW
})

export type Booking = z.infer<typeof BookingSchema>
```

### 1.6 Update index.ts

**File**: `packages/types/src/index.ts`

```typescript
export * from './review'
// ... existing exports
```

---

## Phase 2: API Layer Updates

### 2.1 Create Review API

**File**: `packages/api/src/reviews.ts` (NEW)

```typescript
import { apiClient } from './client';
import type { Review, CreateReviewPayload } from '@mishwari/types';

export const reviewsApi = {
  create: (data: CreateReviewPayload) =>
    apiClient.post<Review>('/reviews/', data).then(res => res.data),

  getMyReviews: () =>
    apiClient.get<Review[]>('/reviews/').then(res => res.data),

  getById: (id: number) =>
    apiClient.get<Review>(`/reviews/${id}/`).then(res => res.data),
};
```

### 2.2 Update Bookings API

**File**: `packages/api/src/bookings.ts`

```typescript
export const bookingsApi = {
  // ... existing methods

  complete: (id: number) =>
    apiClient.post(`/booking/${id}/complete/`).then(res => res.data),
};
```

### 2.3 Update API index

**File**: `packages/api/src/index.ts`

```typescript
export * from './reviews'
// ... existing exports
```

---

## Phase 3: Passenger-Web Updates

### 3.1 Update Trip Card Component

**File**: `apps/passenger-web/src/components/ModernTripCard.tsx`

```typescript
// Replace defaultRating with actual data
const operatorRating = trip.operator?.avg_rating || 0;
const ratingStyle = getRatingColor(operatorRating);

// Update rating display
<div className={`flex items-center gap-1 px-2 py-0.5 rounded-md border shadow-sm ${ratingStyle.bg} ${ratingStyle.text} ${ratingStyle.border}`}>
  <StarIcon className={`w-3 h-3 fill-current`} />
  <span className='text-[10px] font-bold'>{operatorRating.toFixed(1)}</span>
  {trip.operator?.total_reviews > 0 && (
    <span className='text-[9px] opacity-70'>({trip.operator.total_reviews})</span>
  )}
</div>

// Update amenities to use boolean flags
{trip.bus?.has_wifi && <Wifi className='w-3 h-3 text-slate-400' />}
{trip.bus?.has_ac && <Wind className='w-3 h-3 text-slate-400' />}
{trip.bus?.has_usb_charging && <Zap className='w-3 h-3 text-slate-400' />}
```

### 3.2 Create Review Modal Component

**File**: `apps/passenger-web/src/components/ReviewModal.tsx` (NEW)

```typescript
import { useState } from 'react';
import { StarIcon } from '@heroicons/react/24/solid';
import { StarIcon as StarOutline } from '@heroicons/react/24/outline';
import { reviewsApi } from '@mishwari/api';
import type { Booking } from '@mishwari/types';

interface ReviewModalProps {
  booking: Booking;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function ReviewModal({ booking, isOpen, onClose, onSuccess }: ReviewModalProps) {
  const [ratings, setRatings] = useState({
    overall: 0,
    bus: 0,
    driver: 0,
  });
  const [comment, setComment] = useState('');
  const [loading, setLoading] = useState(false);

  const RatingStars = ({ value, onChange, label }: any) => (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onClick={() => onChange(star)}
            className="focus:outline-none"
          >
            {star <= value ? (
              <StarIcon className="w-8 h-8 text-yellow-400" />
            ) : (
              <StarOutline className="w-8 h-8 text-gray-300" />
            )}
          </button>
        ))}
      </div>
    </div>
  );

  const handleSubmit = async () => {
    if (ratings.overall === 0 || ratings.bus === 0 || ratings.driver === 0) {
      alert('يرجى تقييم جميع الجوانب');
      return;
    }

    setLoading(true);
    try {
      await reviewsApi.create({
        booking: booking.id,
        overall_rating: ratings.overall,
        bus_condition_rating: ratings.bus,
        driver_rating: ratings.driver,
        comment,
      });
      onSuccess();
      onClose();
    } catch (error) {
      console.error('Error submitting review:', error);
      alert('فشل إرسال التقييم');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-6">
        <h2 className="text-xl font-bold text-center">تقييم الرحلة</h2>
        
        <div className="space-y-4">
          <RatingStars
            value={ratings.overall}
            onChange={(v: number) => setRatings({ ...ratings, overall: v })}
            label="التقييم العام"
          />
          
          <RatingStars
            value={ratings.bus}
            onChange={(v: number) => setRatings({ ...ratings, bus: v })}
            label="حالة الحافلة"
          />
          
          <RatingStars
            value={ratings.driver}
            onChange={(v: number) => setRatings({ ...ratings, driver: v })}
            label="السائق"
          />

          <div>
            <label className="text-sm font-medium">تعليق (اختياري)</label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="w-full mt-2 p-3 border rounded-lg"
              rows={3}
              placeholder="شارك تجربتك..."
            />
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 border rounded-lg font-medium"
            disabled={loading}
          >
            إلغاء
          </button>
          <button
            onClick={handleSubmit}
            className="flex-1 py-3 bg-brand-primary text-white rounded-lg font-medium"
            disabled={loading}
          >
            {loading ? 'جاري الإرسال...' : 'إرسال التقييم'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 3.3 Update Booking Detail Page

**File**: `apps/passenger-web/src/pages/my_trips/[bookingId].tsx`

```typescript
import { useState } from 'react';
import ReviewModal from '@/components/ReviewModal';

// Inside component
const [showReviewModal, setShowReviewModal] = useState(false);

// Add review button for completed bookings
{booking.status === 'completed' && !booking.review && (
  <button
    onClick={() => setShowReviewModal(true)}
    className="w-full py-3 bg-yellow-500 text-white rounded-lg font-bold"
  >
    تقييم الرحلة
  </button>
)}

{booking.review && (
  <div className="bg-green-50 border border-green-200 rounded-lg p-4">
    <p className="text-sm font-medium text-green-800">تم التقييم</p>
    <div className="flex gap-2 mt-2">
      <span>⭐ {booking.review.overall_rating}/5</span>
    </div>
  </div>
)}

<ReviewModal
  booking={booking}
  isOpen={showReviewModal}
  onClose={() => setShowReviewModal(false)}
  onSuccess={() => {
    // Refresh booking data
    fetchBooking();
  }}
/>
```

### 3.4 Update MiniTicket Component

**File**: `apps/passenger-web/src/components/MiniTicket.tsx`

```typescript
// Add review indicator
{booking.status === 'completed' && (
  <div className="mt-2">
    {booking.review ? (
      <span className="text-xs text-green-600 font-medium">✓ تم التقييم</span>
    ) : (
      <span className="text-xs text-yellow-600 font-medium">⭐ قيّم الرحلة</span>
    )}
  </div>
)}
```

---

## Phase 4: Driver-Web Updates

### 4.1 Update Trip Card Component

**File**: `apps/driver-web/src/components/trips/TripCard.tsx`

```typescript
// Add operator rating display
<div className="flex items-center gap-2 text-sm">
  <span className="text-gray-500">التقييم:</span>
  <div className="flex items-center gap-1">
    <StarIcon className="w-4 h-4 text-yellow-400" />
    <span className="font-semibold">
      {trip.operator?.avg_rating?.toFixed(1) || 'N/A'}
    </span>
    {trip.operator?.total_reviews > 0 && (
      <span className="text-gray-400 text-xs">
        ({trip.operator.total_reviews})
      </span>
    )}
  </div>
</div>
```

### 4.2 Create Complete Booking Action

**File**: `apps/driver-web/src/pages/trips/[id]/bookings/[bookingId].tsx`

```typescript
import { bookingsApi } from '@mishwari/api';

const handleCompleteBooking = async () => {
  if (!confirm('هل تريد تأكيد اكتمال هذه الحجز؟')) return;
  
  try {
    await bookingsApi.complete(booking.id);
    alert('تم تأكيد اكتمال الحجز');
    // Refresh booking
    fetchBooking();
  } catch (error) {
    console.error('Error completing booking:', error);
    alert('فشل تأكيد الحجز');
  }
};

// Add button for active bookings
{booking.status === 'active' && (
  <button
    onClick={handleCompleteBooking}
    className="w-full py-3 bg-green-600 text-white rounded-lg font-bold"
  >
    تأكيد اكتمال الرحلة
  </button>
)}
```

### 4.3 Add Resource Swap Feature

**File**: `apps/driver-web/src/pages/trips/[id]/index.tsx`

```typescript
const [showSwapModal, setShowSwapModal] = useState(false);

// Add swap button for operator_admin
{userRole === 'operator_admin' && trip.status === 'published' && (
  <button
    onClick={() => setShowSwapModal(true)}
    className="px-4 py-2 bg-yellow-500 text-white rounded-lg"
  >
    تغيير الحافلة/السائق
  </button>
)}
```

### 4.4 Create Resource Swap Modal

**File**: `apps/driver-web/src/components/trips/ResourceSwapModal.tsx` (NEW)

```typescript
import { useState } from 'react';
import { apiClient } from '@mishwari/api';

interface ResourceSwapModalProps {
  trip: Trip;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function ResourceSwapModal({ trip, isOpen, onClose, onSuccess }: ResourceSwapModalProps) {
  const [actualBus, setActualBus] = useState<number | null>(null);
  const [actualDriver, setActualDriver] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await apiClient.post(`/operator/trips/${trip.id}/set-actual-resources/`, {
        actual_bus: actualBus,
        actual_driver: actualDriver,
      });
      onSuccess();
      onClose();
    } catch (error) {
      console.error('Error swapping resources:', error);
      alert('فشل تغيير الموارد');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-6">
        <h2 className="text-xl font-bold">تغيير الحافلة/السائق</h2>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">الحافلة الفعلية</label>
            <select
              value={actualBus || ''}
              onChange={(e) => setActualBus(Number(e.target.value))}
              className="w-full p-3 border rounded-lg"
            >
              <option value="">اختر حافلة</option>
              {/* Populate with available buses */}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">السائق الفعلي</label>
            <select
              value={actualDriver || ''}
              onChange={(e) => setActualDriver(Number(e.target.value))}
              className="w-full p-3 border rounded-lg"
            >
              <option value="">اختر سائق</option>
              {/* Populate with available drivers */}
            </select>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 border rounded-lg"
            disabled={loading}
          >
            إلغاء
          </button>
          <button
            onClick={handleSubmit}
            className="flex-1 py-3 bg-brand-primary text-white rounded-lg"
            disabled={loading}
          >
            {loading ? 'جاري الحفظ...' : 'حفظ'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## Phase 5: UI Components Library

### 5.1 Create Rating Display Component

**File**: `packages/ui-web/src/RatingDisplay.tsx` (NEW)

```typescript
import { StarIcon } from '@heroicons/react/24/solid';

interface RatingDisplayProps {
  rating: number;
  totalReviews?: number;
  size?: 'sm' | 'md' | 'lg';
  showCount?: boolean;
}

export default function RatingDisplay({ 
  rating, 
  totalReviews = 0, 
  size = 'md',
  showCount = true 
}: RatingDisplayProps) {
  const sizeClasses = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  };

  const iconSizes = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
  };

  const getRatingColor = (score: number) => {
    if (score >= 4.5) return 'text-green-600';
    if (score >= 4.0) return 'text-yellow-600';
    return 'text-orange-600';
  };

  return (
    <div className={`flex items-center gap-1 ${sizeClasses[size]}`}>
      <StarIcon className={`${iconSizes[size]} ${getRatingColor(rating)}`} />
      <span className="font-bold">{rating.toFixed(1)}</span>
      {showCount && totalReviews > 0 && (
        <span className="text-gray-400">({totalReviews})</span>
      )}
    </div>
  );
}
```

---

## Phase 6: Testing Checklist

### 6.1 Passenger-Web Tests
- [ ] Trip search displays operator ratings
- [ ] Amenity icons use boolean flags
- [ ] Completed bookings show review button
- [ ] Review modal submits successfully
- [ ] Already reviewed bookings show indicator
- [ ] Review appears in booking details

### 6.2 Driver-Web Tests
- [ ] Trip cards show operator rating
- [ ] Complete booking action works
- [ ] Resource swap modal (operator_admin only)
- [ ] Actual resources saved correctly

---

## Summary of Changes by Application

| Application | Files Changed | New Files |
|-------------|---------------|-----------|
| **packages/types** | operator.ts, bus.ts, driver.ts, booking.ts | review.ts |
| **packages/api** | bookings.ts | reviews.ts |
| **passenger-web** | ModernTripCard.tsx, [bookingId].tsx, MiniTicket.tsx | ReviewModal.tsx |
| **driver-web** | TripCard.tsx, [bookingId].tsx, [id]/index.tsx | ResourceSwapModal.tsx |
| **packages/ui-web** | - | RatingDisplay.tsx |

---

## Implementation Order

1. ✅ Update type definitions (packages/types)
2. ✅ Create API methods (packages/api)
3. ✅ Update passenger-web trip display
4. ✅ Add review functionality (passenger-web)
5. ✅ Update driver-web trip display
6. ✅ Add complete booking action (driver-web)
7. ✅ Add resource swap feature (driver-web)
8. ✅ Create shared UI components
9. ✅ Testing

---

## Key Features

### For Passengers
- View operator/bus/driver ratings before booking
- Submit reviews after completed trips
- See amenities using clear icons
- Track review status in booking history

### For Drivers/Operators
- View own ratings and reviews
- Mark bookings as completed
- Swap resources if needed (operator_admin)
- Track performance metrics

---

**Document Version**: 1.0  
**Last Updated**: 2024  
**Status**: Ready for Implementation
