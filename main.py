#!/usr/bin/env python3
"""
🏗️ Railway Infrastructure Setup & FastAPI Application
====================================================

Production FastAPI application with PostgreSQL, Redis, and Stripe integration
optimized for Railway.app deployment.
"""

from fastapi import FastAPI, HTTPException, Depends, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import asyncio
import stripe
from datetime import datetime, timedelta
import jwt
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, EmailStr
import asyncpg
import redis.asyncio as redis
import hashlib
import uuid

# Environment configuration
DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "development")

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

# FastAPI app initialization
app = FastAPI(
    title="ASIS Research Platform API",
    description="AI-powered research platform for academic and corporate users",
    version="1.0.0",
    docs_url="/docs" if ENVIRONMENT == "development" else None
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://research.asisai.com", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Pydantic models
class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    institution: str
    role: str = "researcher"

class SubscriptionCreate(BaseModel):
    tier: str
    billing_period: str  # monthly or annual
    payment_method_id: str

class ResearchQuery(BaseModel):
    query: str
    databases: List[str] = ["pubmed", "arxiv", "crossref"]
    max_results: int = 50

class UserResponse(BaseModel):
    user_id: str
    email: str
    institution: str
    tier: str
    subscription_status: str
    created_date: datetime

# Database connection pool
db_pool = None
redis_client = None

@app.on_event("startup")
async def startup_event():
    """Initialize database and Redis connections"""
    global db_pool, redis_client
    
    # PostgreSQL connection
    if DATABASE_URL:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        
        # Create tables if they don't exist
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR UNIQUE NOT NULL,
                    password_hash VARCHAR NOT NULL,
                    institution VARCHAR,
                    role VARCHAR DEFAULT 'researcher',
                    tier VARCHAR DEFAULT 'academic',
                    subscription_status VARCHAR DEFAULT 'active',
                    is_academic BOOLEAN DEFAULT FALSE,
                    discount_percentage FLOAT DEFAULT 0,
                    created_date TIMESTAMP DEFAULT NOW(),
                    last_active TIMESTAMP DEFAULT NOW(),
                    monthly_usage JSONB DEFAULT '{}'::jsonb
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    subscription_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(user_id),
                    stripe_subscription_id VARCHAR,
                    tier VARCHAR NOT NULL,
                    status VARCHAR DEFAULT 'active',
                    billing_period VARCHAR DEFAULT 'monthly',
                    current_period_start TIMESTAMP,
                    current_period_end TIMESTAMP,
                    created_date TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS research_queries (
                    query_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(user_id),
                    query_text TEXT NOT NULL,
                    databases VARCHAR[],
                    results_count INTEGER,
                    processing_time_ms INTEGER,
                    created_date TIMESTAMP DEFAULT NOW()
                )
            """)
    
    # Redis connection
    if REDIS_URL:
        redis_client = redis.from_url(REDIS_URL)

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections"""
    global db_pool, redis_client
    
    if db_pool:
        await db_pool.close()
    
    if redis_client:
        await redis_client.close()

# Authentication functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify JWT token"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

# API Routes

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "ASIS Research Platform API",
        "version": "1.0.0",
        "status": "active",
        "environment": ENVIRONMENT
    }

@app.get("/health")
async def health_check():
    """Detailed health check for Railway"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # Check database
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health_status["services"]["database"] = "connected"
        except Exception as e:
            health_status["services"]["database"] = f"error: {str(e)}"
            health_status["status"] = "degraded"
    
    # Check Redis
    if redis_client:
        try:
            await redis_client.ping()
            health_status["services"]["redis"] = "connected"
        except Exception as e:
            health_status["services"]["redis"] = f"error: {str(e)}"
            health_status["status"] = "degraded"
    
    return health_status

@app.post("/auth/register")
async def register_user(user_data: UserRegistration):
    """Register new user with academic discount detection"""
    
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    # Check if user already exists
    async with db_pool.acquire() as conn:
        existing_user = await conn.fetchrow(
            "SELECT user_id FROM users WHERE email = $1", user_data.email
        )
        if existing_user:
            raise HTTPException(status_code=400, detail="User already exists")
        
        # Check for academic discount
        is_academic = user_data.email.endswith('.edu') or '.ac.' in user_data.email
        discount = 50 if is_academic else 0
        
        # Hash password
        password_hash = hashlib.sha256(user_data.password.encode()).hexdigest()
        
        # Insert user
        user_id = await conn.fetchval("""
            INSERT INTO users (email, password_hash, institution, role, is_academic, discount_percentage)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING user_id
        """, user_data.email, password_hash, user_data.institution, user_data.role, is_academic, discount)
        
        # Create access token
        access_token = create_access_token(data={"sub": str(user_id)})
        
        return {
            "user_id": str(user_id),
            "access_token": access_token,
            "token_type": "bearer",
            "is_academic": is_academic,
            "discount_percentage": discount
        }

@app.post("/auth/login")
async def login_user(email: EmailStr, password: str):
    """User login"""
    
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with db_pool.acquire() as conn:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        user = await conn.fetchrow(
            "SELECT user_id, email, tier, subscription_status FROM users WHERE email = $1 AND password_hash = $2",
            email, password_hash
        )
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Update last active
        await conn.execute(
            "UPDATE users SET last_active = NOW() WHERE user_id = $1", user['user_id']
        )
        
        access_token = create_access_token(data={"sub": str(user['user_id'])})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": str(user['user_id']),
            "tier": user['tier'],
            "subscription_status": user['subscription_status']
        }

@app.post("/subscriptions/create")
async def create_subscription(
    subscription_data: SubscriptionCreate,
    user_id: str = Depends(verify_token)
):
    """Create Stripe subscription"""
    
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    # Pricing mapping
    pricing = {
        "academic": {"monthly": 4950, "annual": 49500},  # 50% academic discount
        "professional": {"monthly": 29900, "annual": 299000},
        "enterprise": {"monthly": 99900, "annual": 999000}
    }
    
    if subscription_data.tier not in pricing:
        raise HTTPException(status_code=400, detail="Invalid tier")
    
    amount = pricing[subscription_data.tier][subscription_data.billing_period]
    
    try:
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT email, is_academic FROM users WHERE user_id = $1", uuid.UUID(user_id)
            )
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Create Stripe customer
            customer = stripe.Customer.create(
                email=user['email'],
                payment_method=subscription_data.payment_method_id,
                invoice_settings={'default_payment_method': subscription_data.payment_method_id}
            )
            
            # Create subscription
            stripe_subscription = stripe.Subscription.create(
                customer=customer.id,
                items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': f'ASIS Research Platform - {subscription_data.tier.title()}'},
                        'unit_amount': amount,
                        'recurring': {'interval': subscription_data.billing_period.replace('ly', '')}
                    }
                }],
                metadata={'user_id': user_id, 'tier': subscription_data.tier}
            )
            
            # Save subscription to database
            await conn.execute("""
                INSERT INTO subscriptions (user_id, stripe_subscription_id, tier, billing_period, current_period_start, current_period_end)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, uuid.UUID(user_id), stripe_subscription.id, subscription_data.tier,
                subscription_data.billing_period,
                datetime.fromtimestamp(stripe_subscription.current_period_start),
                datetime.fromtimestamp(stripe_subscription.current_period_end)
            )
            
            # Update user tier
            await conn.execute(
                "UPDATE users SET tier = $1, subscription_status = 'active' WHERE user_id = $2",
                subscription_data.tier, uuid.UUID(user_id)
            )
            
            return {
                "subscription_id": stripe_subscription.id,
                "status": stripe_subscription.status,
                "tier": subscription_data.tier,
                "amount": amount,
                "current_period_end": datetime.fromtimestamp(stripe_subscription.current_period_end).isoformat()
            }
    
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/research/search")
async def search_research(
    query_data: ResearchQuery,
    user_id: str = Depends(verify_token)
):
    """Execute research search across multiple databases"""
    
    start_time = datetime.utcnow()
    
    # Import the real data integration engine
    from asis_real_data_integration_engine import ASISRealDataEngine, APICredentials
    
    try:
        # Initialize research engine
        credentials = APICredentials(crossref_email="api@asisai.com")
        engine = ASISRealDataEngine(credentials)
        
        # Execute search
        results = await engine.search_comprehensive(
            query_data.query, 
            max_results=query_data.max_results
        )
        
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Log query to database
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO research_queries (user_id, query_text, databases, results_count, processing_time_ms)
                    VALUES ($1, $2, $3, $4, $5)
                """, uuid.UUID(user_id), query_data.query, query_data.databases, len(results), int(processing_time))
        
        # Format results for API response
        formatted_results = []
        for doc in results:
            formatted_results.append({
                "title": doc.title,
                "authors": doc.authors,
                "abstract": doc.abstract[:500] + "..." if doc.abstract and len(doc.abstract) > 500 else doc.abstract,
                "publication_date": doc.publication_date.isoformat() if doc.publication_date else None,
                "source": doc.source,
                "doi": doc.doi,
                "citations": doc.citations,
                "quality_score": doc.quality_score.value,
                "url": doc.url
            })
        
        return {
            "query": query_data.query,
            "results_count": len(results),
            "processing_time_ms": int(processing_time),
            "databases_searched": query_data.databases,
            "results": formatted_results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/users/profile")
async def get_user_profile(user_id: str = Depends(verify_token)):
    """Get user profile information"""
    
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("""
            SELECT user_id, email, institution, role, tier, subscription_status,
                   is_academic, discount_percentage, created_date, last_active, monthly_usage
            FROM users WHERE user_id = $1
        """, uuid.UUID(user_id))
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "user_id": str(user['user_id']),
            "email": user['email'],
            "institution": user['institution'],
            "role": user['role'],
            "tier": user['tier'],
            "subscription_status": user['subscription_status'],
            "is_academic": user['is_academic'],
            "discount_percentage": user['discount_percentage'],
            "created_date": user['created_date'].isoformat(),
            "last_active": user['last_active'].isoformat(),
            "monthly_usage": user['monthly_usage']
        }

@app.get("/admin/stats")
async def get_admin_stats(user_id: str = Depends(verify_token)):
    """Get platform statistics for admin users"""
    
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with db_pool.acquire() as conn:
        # Verify admin access
        user_role = await conn.fetchval(
            "SELECT role FROM users WHERE user_id = $1", uuid.UUID(user_id)
        )
        
        if user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get statistics
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_subscriptions = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE status = 'active'"
        )
        total_queries = await conn.fetchval("SELECT COUNT(*) FROM research_queries")
        
        # Revenue calculation (simplified)
        revenue_data = await conn.fetch("""
            SELECT tier, COUNT(*) as count FROM subscriptions 
            WHERE status = 'active' GROUP BY tier
        """)
        
        monthly_revenue = 0
        for row in revenue_data:
            tier_prices = {"academic": 49.5, "professional": 299, "enterprise": 999}
            monthly_revenue += tier_prices.get(row['tier'], 0) * row['count']
        
        return {
            "total_users": total_users,
            "active_subscriptions": active_subscriptions,
            "total_queries": total_queries,
            "estimated_monthly_revenue": monthly_revenue,
            "timestamp": datetime.utcnow().isoformat()
        }

# Stripe webhook handler
@app.post("/webhooks/stripe")
async def stripe_webhook(request):
    """Handle Stripe webhook events"""
    
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle subscription events
    if event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        # Update subscription in database
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE subscriptions SET status = $1, current_period_end = $2
                    WHERE stripe_subscription_id = $3
                """, subscription['status'],
                    datetime.fromtimestamp(subscription['current_period_end']),
                    subscription['id']
                )
    
    return {"received": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
