import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchTradingState, triggerKillSwitch } from '../api/risk';

export function useTradingState() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['tradingState'],
    queryFn: fetchTradingState,
  });

  const killSwitchMutation = useMutation({
    mutationFn: triggerKillSwitch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tradingState'] });
    },
  });

  return {
    ...query,
    triggerKillSwitch: killSwitchMutation.mutateAsync,
  };
}
