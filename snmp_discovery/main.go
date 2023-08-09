package main

import (
	"fmt"
	"github.com/bigkevmcd/go-configparser"
	"github.com/hallidave/mibtool/smi"
	"log"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gosnmp/gosnmp"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
	"github.com/spf13/viper"
)

const DefaultMetadataMaxInstance = 1500
const IfSectionName = "insightfinder"

var (
	configPath            = "./conf.d"
	defaultConfigFilename = "config"
	defaultIniSectionName = "snmp_discovery"
	ifConfig              = make(map[string]interface{})
)

type snmpDataValue struct {
	Host  string      `json:"host,omitempty" validate:"required"`
	Name  string      `json:"name,omitempty" validate:"required"`
	Value interface{} `json:"value,omitempty" validate:"required"`
}

func incIP(ip net.IP) {
	for j := len(ip) - 1; j >= 0; j-- {
		ip[j]++
		if ip[j] > 0 {
			break
		}
	}
}

func handleWalkResult(oidNames map[string]string, host string, resultChan chan snmpDataValue) gosnmp.WalkFunc {
	return func(pdu gosnmp.SnmpPDU) error {

		// The oid might have . as prefix or .n as postfix
		oid := pdu.Name

		name, ok := oidNames[oid]
		if !ok {
			// remove the . prefix and try again
			if strings.HasPrefix(oid, ".") {
				oid = oid[1:]
				name, ok = oidNames[oid]
			}
		}

		if !ok {
			// Try to remove the last digit
			parts := strings.Split(oid, ".")
			oid = strings.Join(parts[:len(parts)-1], ".")
			name, ok = oidNames[oid]
			if ok {
				name += "." + parts[len(parts)-1]
			}
		}

		if !ok {
			return nil
		}

		if pdu.Type == gosnmp.Counter32 || pdu.Type == gosnmp.Counter64 || pdu.Type == gosnmp.Integer || pdu.Type == gosnmp.Uinteger32 {
			value := fmt.Sprint(gosnmp.ToBigInt(pdu.Value))
			resultChan <- snmpDataValue{Host: host, Name: name, Value: value}
		}
		return nil
	}
}

func snmpTrapHandler(packet *gosnmp.SnmpPacket, addr *net.UDPAddr) {
	log.Printf("SNMP trap received from: %s:%d. Community:%s, SnmpVersion:%s\n",
		addr.IP, addr.Port, packet.Community, packet.Version)
	for i, variable := range packet.Variables {
		var val string
		switch variable.Type {
		case gosnmp.OctetString:
			val = string(variable.Value.([]byte))
		case gosnmp.ObjectIdentifier:
			val = fmt.Sprintf("%s", variable.Value)
		case gosnmp.TimeTicks:
			a := gosnmp.ToBigInt(variable.Value)
			val = fmt.Sprintf("%d", (*a).Int64())
		case gosnmp.Null:
			val = ""
		default:
			a := gosnmp.ToBigInt(variable.Value)
			val = fmt.Sprintf("%d", (*a).Int64())
		}
		log.Printf("- oid[%d]: %s (%s) = %v \n", i, variable.Name, variable.Type, val)
	}
}

func snmpTrapServer(address string) {
	tl := gosnmp.NewTrapListener()
	tl.OnNewTrap = snmpTrapHandler
	tl.Params = gosnmp.Default
	tl.Params.Logger = gosnmp.NewLogger(log.New(os.Stdout, "", 0))

	err := tl.Listen(address)
	if err != nil {
		time.Sleep(1 * time.Second)
		log.Fatalf("Error in TRAP listen: %s\n", err)
	}
}

func snmpDiscovery(ipRange string, port int, community string, mibDirs string, modules string, oid string) {
	// Use nmap to scan the network for hosts with the specified port open
	// hosts := nmapScan(ipRange, port)
	ranges := strings.Split(ipRange, ",")
	hosts := make([]string, 0)

	mibPaths := strings.Split(mibDirs, ",")
	mib := smi.NewMIB(mibPaths...)
	mib.Debug = true

	// Load the MIB modules
	err := mib.LoadModules(strings.Split(modules, ",")...)
	if err != nil {
		log.Fatal(err)
	}

	// Build the oid to name mapping
	oidNames := make(map[string]string)

	mib.VisitSymbols(func(sym *smi.Symbol, oid smi.OID) {
		oidNames[oid.String()] = sym.Name
	})

	for _, r := range ranges {
		if len(strings.TrimSpace(r)) > 0 {
			_, ipnet, err := net.ParseCIDR(r)
			if err != nil {
				log.Printf("Failed to parse CIDR %s, will try to parse the input as IP address. error: %v", r, err)

				ipAddress := net.ParseIP(r)
				if ipAddress == nil {
					_ = log.Output(1, "Failed to pass the IP address, ignore.")
				}
				hosts = append(hosts, ipAddress.String())
				continue
			}

			for ip := ipnet.IP.Mask(ipnet.Mask); ipnet.Contains(ip); incIP(ip) {
				hosts = append(hosts, ip.String())
			}
		}
	}

	var wg sync.WaitGroup

	// Create a channel to receive SNMP results
	// resultChan := make(chan *gosnmp.SnmpPacket)
	resultChan := make(chan snmpDataValue)

	// Use the results to print an example output
	for _, host := range hosts {

		wg.Add(1)

		host := host
		go func() {
			defer wg.Done()

			gs := &gosnmp.GoSNMP{
				Target:    host,
				Port:      uint16(port),
				Community: community,
				Version:   gosnmp.Version2c,
				Timeout:   time.Duration(5) * time.Second,
			}
			err := gs.Connect()
			if err != nil {
				fmt.Printf("[ERROR] SNMP connect failed at %s:%v, error: %v\n", host, port, err)
				return
			}

			defer func(Conn net.Conn) {
				_ = Conn.Close()
			}(gs.Conn)

			_ = log.Output(1, "Processing the host: "+host)
			err = gs.BulkWalk(oid, handleWalkResult(oidNames, host, resultChan))
			if err != nil {
				fmt.Printf("[ERROR] SNMP walk failed at %s:%v, error: %v\n", host, port, err)
				return
			}
		}()
	}

	// Wait for all goroutines to finish
	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Process SNMP results
	hostData := make(map[string]map[string]interface{})
	for result := range resultChan {
		if _, ok := hostData[result.Host]; !ok {
			hostData[result.Host] = make(map[string]interface{})
		}
		hostData[result.Host][result.Name] = result.Value
	}
	processSNMPResult(hostData)
}

func processSNMPResult(hostData map[string]map[string]interface{}) {
	payload := make(map[string]InstanceData)

	for instanceName, data := range hostData {
		timeStamp := time.Now().UnixMilli()

		instanceData, ok := payload[instanceName]
		if !ok {
			// Current Instance didn't exist
			instanceData = InstanceData{
				InstanceName:       instanceName,
				ComponentName:      instanceName,
				DataInTimestampMap: make(map[int64]DataInTimestamp),
			}
			payload[instanceName] = instanceData
		}

		dataInTimestampMap, ok := instanceData.DataInTimestampMap[timeStamp]
		if !ok {
			dataInTimestampMap = DataInTimestamp{
				TimeStamp:        timeStamp,
				MetricDataPoints: make([]MetricDataPoint, 0),
			}
		}

		metricDataPoints := dataInTimestampMap.MetricDataPoints
		for metric, val := range data {
			intVar, _ := strconv.ParseFloat(ToString(val), 64)
			metricDP := MetricDataPoint{
				MetricName: metric,
				Value:      intVar,
			}
			metricDataPoints = append(metricDataPoints, metricDP)
		}
		dataInTimestampMap.MetricDataPoints = metricDataPoints
		instanceData.DataInTimestampMap[timeStamp] = dataInTimestampMap

	}
	sendMetricData(payload, ifConfig)
}

func absFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	curdir, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	mydir, err := filepath.Abs(curdir)
	if err != nil {
		panic(err)
	}
	return filepath.Join(mydir, filename)
}

func NewTrapCommand() *cobra.Command {

	address := ""

	trapCmd := &cobra.Command{
		Use:   "trap",
		Short: "Start trap service",
		PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
			return initializeConfig(cmd)
		}, Run: func(cmd *cobra.Command, args []string) {
			log.Printf("Starting SNMP TRAP Server on: %s\n", address)
			snmpTrapServer(address)
		},
	}

	trapCmd.Flags().StringVarP(&address, "address", "a", "0.0.0.0:162", "SNMP trap server address")

	return trapCmd
}

func NewScanCommand() *cobra.Command {
	ipRange := ""
	community := ""
	oid := ""
	port := 0
	midDirs := ""
	modules := ""

	scanCmd := &cobra.Command{
		Use:   "scan",
		Short: "Scan snmp devices",
		PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
			err := initializeConfig(cmd)
			if err != nil {
				return err
			}

			initializeIFSettings()
			return nil
		}, Run: func(cmd *cobra.Command, args []string) {

			println("snmp scanning with ip range:", ipRange, ",community:", community, ",oid:", oid, ",port:", port, ",midDirs:", midDirs, ",modules:", modules)
			snmpDiscovery(ipRange, port, community, midDirs, modules, oid)
		},
	}

	scanCmd.Flags().StringVarP(&ipRange, "ip-range", "", "0.0.0.0/32", "ip range to discover the devices")
	scanCmd.Flags().IntVarP(&port, "port", "p", 161, "the port to use for the SNMP connection")
	scanCmd.Flags().StringVarP(&community, "community", "c", "public", "What is the community string?")
	scanCmd.Flags().StringVarP(&midDirs, "mid-dirs", "", "/usr/share/snmp/mibs", "folder path to store mid definitions, split by commas")
	scanCmd.Flags().StringVarP(&modules, "modules", "", "UCD-SNMP-MIB,UCD-DISKIO-MIB", "mid modules to use, split by commas")
	scanCmd.Flags().StringVarP(&oid, "oid", "o", "", "the mid/oid defining a subtree of values, split by commas")

	return scanCmd
}

func NewRootCommand() *cobra.Command {

	rootCmd := &cobra.Command{
		Use:   "snmp_discovery",
		Short: "Using SNMP protocol to scan devices and trap devices activities",
		PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
			return initializeConfig(cmd)
		}, Run: func(cmd *cobra.Command, args []string) {
		},
	}

	rootCmd.AddCommand(NewScanCommand())
	rootCmd.AddCommand(NewTrapCommand())

	return rootCmd
}

func initializeConfig(cmd *cobra.Command) error {
	v := viper.New()

	v.SetConfigName(defaultConfigFilename)
	v.SetConfigType("ini")
	v.AddConfigPath(configPath)

	if err := v.ReadInConfig(); err != nil {
		// It's okay if the config file doesn't exist
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return err
		}
	}

	bindFlags(cmd, v)

	return nil
}

func initializeIFSettings() {
	// get if config
	configFilePath := filepath.Join(configPath, defaultConfigFilename+".ini")
	p, err := configparser.NewConfigParserFromFile(configFilePath)
	if err != nil {
		log.Fatal("cannot load config file: "+configFilePath, err)
	}

	ifConfig = getIFConfigsSection(p)

	checkProject(ifConfig)
	return
}

func bindFlags(cmd *cobra.Command, v *viper.Viper) {
	cmd.Flags().VisitAll(func(f *pflag.Flag) {
		configName := f.Name

		sectionName := fmt.Sprintf("%s.%s.%s", defaultIniSectionName, cmd.Use, configName)
		if !f.Changed && (v.IsSet(configName) || v.IsSet(sectionName)) {
			val := v.Get(configName)
			if val == nil {
				val = v.Get(sectionName)
			}
			_ = cmd.Flags().Set(f.Name, val.(string))
		}
	})
}

func getIFConfigsSection(p *configparser.ConfigParser) map[string]interface{} {
	// Required parameters
	var userName = ToString(GetConfigValue(p, IfSectionName, "user_name", true))
	var licenseKey = ToString(GetConfigValue(p, IfSectionName, "license_key", true))
	var projectName = ToString(GetConfigValue(p, IfSectionName, "project_name", true))
	// We use uppercase for project log type.
	var projectType = strings.ToUpper(ToString(GetConfigValue(p, IfSectionName, "project_type", true)))
	var runInterval = ToString(GetConfigValue(p, IfSectionName, "run_interval", true))

	// Optional parameters
	var token = ToString(GetConfigValue(p, IfSectionName, "token", false))
	var systemName = ToString(GetConfigValue(p, IfSectionName, "system_name", false))
	var projectNamePrefix = ToString(GetConfigValue(p, IfSectionName, "project_name_prefix", false))
	var metaDataMaxInstance = ToString(GetConfigValue(p, IfSectionName, "metadata_max_instances", false))
	var samplingInterval = ToString(GetConfigValue(p, IfSectionName, "sampling_interval", false))
	var ifURL = ToString(GetConfigValue(p, IfSectionName, "if_url", false))
	var httpProxy = ToString(GetConfigValue(p, IfSectionName, "if_http_proxy", false))
	var httpsProxy = ToString(GetConfigValue(p, IfSectionName, "if_https_proxy", false))
	var isReplay = ToString(GetConfigValue(p, IfSectionName, "isReplay", false))
	var samplingIntervalInSeconds string

	if len(projectNamePrefix) > 0 && !strings.HasSuffix(projectNamePrefix, "-") {
		projectNamePrefix = projectNamePrefix + "-"
	}

	if !IsValidProjectType(projectType) {
		panic("[ERROR] Non-existing project type: " + projectType + "! Please use the supported project types. ")
	}

	if len(samplingInterval) == 0 {
		if strings.Contains(projectType, "METRIC") {
			panic("[ERROR] InsightFinder configuration [sampling_interval] is required for METRIC project!")
		} else {
			// Set default for non-metric project
			samplingInterval = "10"
			samplingIntervalInSeconds = "600"
		}
	}

	if strings.HasSuffix(samplingInterval, "s") {
		samplingIntervalInSeconds = samplingInterval[:len(samplingInterval)-1]
		samplingIntervalInt, err := strconv.Atoi(samplingInterval)
		if err != nil {
			panic(err)
		}
		samplingInterval = fmt.Sprint(samplingIntervalInt / 60.0)
	} else {
		samplingIntervalInt, err := strconv.Atoi(samplingInterval)
		if err != nil {
			panic(err)
		}
		samplingIntervalInSeconds = fmt.Sprint(int64(samplingIntervalInt * 60))
	}

	isReplay = strconv.FormatBool(strings.Contains(projectType, "REPLAY"))

	if len(metaDataMaxInstance) == 0 {
		metaDataMaxInstance = strconv.FormatInt(int64(DefaultMetadataMaxInstance), 10)
	} else {
		metaDataMaxInstanceInt, err := strconv.Atoi(metaDataMaxInstance)
		if err != nil {
			log.Output(2, err.Error())
			log.Output(2, "[ERROR] Meta data max instance can only be integer number.")
			os.Exit(1)
		}
		if metaDataMaxInstanceInt > DefaultMetadataMaxInstance {
			metaDataMaxInstance = string(rune(metaDataMaxInstanceInt))
		}
	}

	if len(ifURL) == 0 {
		ifURL = "https://app.insightfinder.com"
	}

	ifProxies := make(map[string]string)
	if len(httpProxy) > 0 {
		ifProxies["http"] = httpProxy
	}
	if len(httpsProxy) > 0 {
		ifProxies["https"] = httpsProxy
	}

	configIF := map[string]interface{}{
		"userName":                  userName,
		"licenseKey":                licenseKey,
		"token":                     token,
		"projectName":               projectName,
		"systemName":                systemName,
		"projectNamePrefix":         projectNamePrefix,
		"projectType":               projectType,
		"metaDataMaxInstance":       metaDataMaxInstance,
		"samplingInterval":          samplingInterval,
		"samplingIntervalInSeconds": samplingIntervalInSeconds,
		"runInterval":               runInterval,
		"ifURL":                     ifURL,
		"ifProxies":                 ifProxies,
		"isReplay":                  isReplay,
	}
	return configIF
}

func main() {
	cmd := NewRootCommand()
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
