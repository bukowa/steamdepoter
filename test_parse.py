from bs4 import BeautifulSoup
import datetime

html_content = """
<tbody>
<tr data-branch="public">
<td class="text-right">25 February 2016 – 16:40:17 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2016-02-25T16:40:17+00:00" aria-label="25 February 2016 at 16:40:17 UTC
25 February 2016 at 17:40:17 CEST">10.3 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:5293784631537118660" rel="nofollow">5293784631537118660</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">10 December 2015 – 13:51:24 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-12-10T13:51:24+00:00" aria-label="10 December 2015 at 13:51:24 UTC
10 December 2015 at 14:51:24 CEST">10.4 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:5543653047192420981" rel="nofollow">5543653047192420981</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">1 October 2015 – 13:00:56 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-10-01T13:00:56+00:00" aria-label="1 October 2015 at 13:00:56 UTC
1 October 2015 at 15:00:56 CEST">10.6 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:1175169509889743823" rel="nofollow">1175169509889743823</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">15 September 2015 – 16:00:12 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-09-15T16:00:12+00:00" aria-label="15 September 2015 at 16:00:12 UTC
15 September 2015 at 18:00:12 CEST">10.7 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:8192845233863848138" rel="nofollow">8192845233863848138</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">3 July 2015 – 09:03:37 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-07-03T09:03:37+00:00" aria-label="3 July 2015 at 09:03:37 UTC
3 July 2015 at 11:03:37 CEST">10.8 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:5481083006305862452" rel="nofollow">5481083006305862452</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">25 June 2015 – 16:58:59 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-06-25T16:58:59+00:00" aria-label="25 June 2015 at 16:58:59 UTC
25 June 2015 at 18:58:59 CEST">10.9 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:1769951970719364447" rel="nofollow">1769951970719364447</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">29 April 2015 – 12:58:49 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-04-29T12:58:49+00:00" aria-label="29 April 2015 at 12:58:49 UTC
29 April 2015 at 14:58:49 CEST">11.1 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:848920177893537001" rel="nofollow">848920177893537001</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">21 April 2015 – 09:57:43 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-04-21T09:57:43+00:00" aria-label="21 April 2015 at 09:57:43 UTC
21 April 2015 at 11:57:43 CEST">11.1 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:4789359191890284754" rel="nofollow">4789359191890284754</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">25 March 2015 – 16:06:59 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-03-25T16:06:59+00:00" aria-label="25 March 2015 at 16:06:59 UTC
25 March 2015 at 17:06:59 CEST">11.2 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:5075437672130082438" rel="nofollow">5075437672130082438</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
<tr data-branch="public">
<td class="text-right">4 March 2015 – 10:58:39 UTC</td>
<td class="timeago tooltipped tooltipped-n" data-time="2015-03-04T10:58:39+00:00" aria-label="4 March 2015 at 10:58:39 UTC
4 March 2015 at 11:58:39 CEST">11.2 years ago</td>
<td class="tabular-nums">
<a href="/depot/325623/history/?changeid=M:1739501320785904036" rel="nofollow">1739501320785904036</a>
</td>
<td class="manifest-copy"><svg width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-copy" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg></td>
</tr>
</tbody>
"""

def parse_manifests(html):
    soup = BeautifulSoup(html, 'html.parser')
    manifests = []
    
    # Find all table rows
    for row in soup.find_all('tr'):
        branch = row.get('data-branch')
        if not branch:
            continue
            
        # Time ago (data-time)
        time_td = row.find('td', class_='timeago')
        if not time_td:
            continue
        date_str = time_td.get('data-time')
        
        # Manifest ID
        manifest_td = row.find('td', class_='tabular-nums')
        if not manifest_td:
            continue
            
        a_tag = manifest_td.find('a')
        if not a_tag:
            continue
            
        manifest_id = a_tag.text.strip()
        
        manifests.append({
            'branch': branch,
            'date': date_str,
            'manifest_id': manifest_id
        })
        
    return manifests

if __name__ == "__main__":
    results = parse_manifests(html_content)
    print(f"Found {len(results)} manifests:")
    for res in results:
        print(f"  - Branch: {res['branch']:<10} | Date: {res['date']} | Manifest ID: {res['manifest_id']}")
