#!/bin/bash

declare -i RATE
RATE=0
echo "Enter the number of nonces to burn per iteration at the '>' prompt."
echo "The number of bytes burned per iteration will appear before the next prompt."
echo "CTRL-C to exit"
read -p ">" RATE
coproc { exec 2<&-; exec 1<&-; while [[ 1 ]]; do python3 ./print_nonce.py burn $RATE; done; }
trap "kill $COPROC_PID; echo -e '\nGOODBYTE AND THANKS FOR ALL THE 10101010s'; exit;" 2
re="^[0-9]+$"
while [[ 1 ]]; do
		read -p "$(( $RATE * 8 )) >" REPLY
		if  [[ "$REPLY" =~ $re ]]; then
				RATE=$REPLY
		else
				echo "invalid number"
				continue
		fi
		kill $COPROC_PID
		wait $COPROC_PID 2>/dev/null
		coproc { exec 2<&-; exec 1<&-; while [[ 1 ]]; do ./print_nonce.py burn $RATE; done; }
		trap "kill $COPROC_PID; echo -e '\nGOODBYTE AND THANKS FOR ALL THE 10101010s'; exit;" 2
done

kill $COPROC_PID


