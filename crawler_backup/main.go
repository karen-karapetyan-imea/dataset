package main

import (
	"bufio"
	"crypto/sha1"
	"encoding/csv"
	"fmt"
	"io"
	"math/rand"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const (
	workerCount   = 80
	requestsPerS = 40 // rate limit
	timeout       = 20 * time.Second
	maxRetries    = 2

	outputDir = "output"
	mapFile   = "mapping.csv"
)

type Result struct {
	URL        string
	Filename   string
	StatusCode int
	Error      string
}

func main() {
	rand.Seed(time.Now().UnixNano())

	file, err := os.Open("urls.txt")
	if err != nil {
		panic(err)
	}
	defer file.Close()

	_ = os.MkdirAll(outputDir, 0755)

	jobs := make(chan string, workerCount)
	results := make(chan Result, workerCount)

	// CSV writer
	mapF, _ := os.OpenFile(mapFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	defer mapF.Close()
	csvWriter := csv.NewWriter(mapF)
	defer csvWriter.Flush()

	// Write header once
	if stat, _ := mapF.Stat(); stat.Size() == 0 {
		_ = csvWriter.Write([]string{"url", "filename", "status_code", "error"})
	}

	client := &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			MaxIdleConns:        500,
			MaxIdleConnsPerHost: 100,
			DialContext: (&net.Dialer{
				Timeout:   10 * time.Second,
				KeepAlive: 30 * time.Second,
			}).DialContext,
		},
	}

	limiter := time.Tick(time.Second / requestsPerS)

	// Workers
	var wg sync.WaitGroup
	for i := 0; i < workerCount; i++ {
		wg.Add(1)
		go worker(client, jobs, results, limiter, &wg)
	}

	// Writer goroutine
	go func() {
		for r := range results {
			_ = csvWriter.Write([]string{
				r.URL,
				r.Filename,
				fmt.Sprint(r.StatusCode),
				r.Error,
			})
			csvWriter.Flush()
		}
	}()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		url := strings.TrimSpace(scanner.Text())
		if url != "" {
			jobs <- url
		}
	}

	close(jobs)
	wg.Wait()
	close(results)

	fmt.Println("✅ Crawl finished")
}

func worker(
	client *http.Client,
	jobs <-chan string,
	results chan<- Result,
	limiter <-chan time.Time,
	wg *sync.WaitGroup,
) {
	defer wg.Done()

	for url := range jobs {
		<-limiter // rate limit
		time.Sleep(time.Duration(rand.Intn(300)) * time.Millisecond) // jitter

		filename := hashURL(url) + ".html"
		path := filepath.Join(outputDir, filename)

		var status int
		var errMsg string

		for attempt := 0; attempt <= maxRetries; attempt++ {
			status, errMsg = fetch(client, url, path)
			if errMsg == "" {
				break
			}
			time.Sleep(time.Duration(attempt+1) * time.Second)
		}

		results <- Result{
			URL:        url,
			Filename:   filename,
			StatusCode: status,
			Error:      errMsg,
		}
	}
}

func fetch(client *http.Client, url, path string) (int, string) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return 0, err.Error()
	}

	req.Header.Set("User-Agent", randomUA())
	req.Header.Set("Accept", "text/html")

	resp, err := client.Do(req)
	if err != nil {
		return 0, err.Error()
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return resp.StatusCode, "non-200"
	}

	file, err := os.Create(path)
	if err != nil {
		return resp.StatusCode, err.Error()
	}
	defer file.Close()

	_, err = io.Copy(file, resp.Body)
	if err != nil {
		return resp.StatusCode, err.Error()
	}

	return resp.StatusCode, ""
}

func hashURL(url string) string {
	h := sha1.Sum([]byte(url))
	return fmt.Sprintf("%x", h)
}

func randomUA() string {
	uas := []string{
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
		"Mozilla/5.0 (X11; Linux x86_64)",
	}
	return uas[rand.Intn(len(uas))]
}