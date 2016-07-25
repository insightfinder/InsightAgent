

usage()
{
	echo "Usage: ./stopcron.sh -t AGENT_TYPE
AGENT_TYPE = hypervisor"
}

if [ "$#" -lt 2 ]; then
	usage
	exit 1
fi

while [ "$1" != "" ]; do
	case $1 in
		-t )	shift
			AGENT_TYPE=$1
			;;
		* )	usage
			exit 1
	esac
	shift
done

if [ $AGENT_TYPE != 'hypervisor' ]; then
	usage
	exit 1
fi

if [ -z "$INSIGHTAGENTDIR" ]; then
	export INSIGHTAGENTDIR=`pwd`
fi

TEMPCRON=/var/spool/cron/crontabs/root
sed -i '/InsightAgent-testing/d' $TEMPCRON
	
cronpid=`cat /var/run/crond.pid`
kill $cronpid
crond

echo "Hypervisor agent stopped"
