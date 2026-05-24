-- Step 7 starter SQL for Supabase
-- Recreates high-value analytics used by current Python DB logic.

create index if not exists idx_inventory_ledger_sender_phone on public.inventory_ledger (sender_phone);
create index if not exists idx_inventory_ledger_fabric_shade on public.inventory_ledger (fabric, shade_code);
create index if not exists idx_inventory_ledger_created_at on public.inventory_ledger (created_at desc);

-- Stock status report equivalent to get_stock_status_report
create or replace view public.v_stock_status_report as
select
  sender_phone,
  fabric,
  shade_code,
  sum(case when transaction_type = 'INWARD' then meters else -meters end) as current_meters,
  sum(case when transaction_type = 'INWARD' then thaans else -thaans end) as current_thaans
from public.inventory_ledger
group by sender_phone, fabric, shade_code;

-- Global stats equivalent
create or replace view public.v_global_stats as
select
  sender_phone,
  sum(case when transaction_type = 'INWARD' then meters else 0 end) as total_inward,
  sum(case when transaction_type = 'OUTWARD' then meters else 0 end) as total_outward,
  sum(case when transaction_type = 'INWARD' then meters else -meters end) as net_stock,
  sum(case when transaction_type = 'INWARD' then thaans else -thaans end) as total_thaans
from public.inventory_ledger
group by sender_phone;

-- RPC with optional search (maps to existing behavior)
create or replace function public.get_stock_status_report(
  p_sender_phone text,
  p_search_term text default null,
  p_threshold_meters numeric default 50
)
returns table (
  fabric text,
  shade_code text,
  current_meters numeric,
  current_thaans numeric,
  status text
)
language sql
stable
as $$
  select
    v.fabric,
    v.shade_code,
    v.current_meters,
    v.current_thaans,
    case
      when v.current_meters <= 0 then 'OUT_OF_STOCK'
      when v.current_meters < p_threshold_meters then 'LOW_STOCK'
      else 'HEALTHY'
    end as status
  from public.v_stock_status_report v
  where v.sender_phone = p_sender_phone
    and (
      p_search_term is null
      or v.fabric ilike '%' || p_search_term || '%'
      or v.shade_code ilike '%' || p_search_term || '%'
    )
  order by v.fabric asc, v.shade_code asc;
$$;
