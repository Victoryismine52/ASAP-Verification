import os
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault('ELIGIBILITY_PROVIDER', 'mock')
os.environ['DATABASE_URL'] = 'sqlite:///./test_asap.db'

from app.main import app
from app.db import Base, engine


@pytest.mark.asyncio
async def test_demo_load_counts_delete_and_filters_and_exports():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        r1 = await client.post('/demo/load')
        assert r1.status_code == 200
        r2 = await client.post('/demo/load')
        assert r2.status_code == 200
        assert r2.json()['work_items']['inserted'] == 0

        counts = await client.get('/demo/counts')
        assert counts.status_code == 200
        assert counts.json()['work_items']['demo'] >= 10

        only = await client.get('/work-items', params={'demo': 'only'})
        excl = await client.get('/work-items', params={'demo': 'exclude'})
        allr = await client.get('/work-items', params={'demo': 'all'})
        assert len(only.json()['items']) >= 10
        assert len(excl.json()['items']) == 0
        assert len(allr.json()['items']) >= len(only.json()['items'])

        exp = await client.get('/work-items/export.csv')
        assert 'Demo1' not in exp.text
        exp2 = await client.get('/work-items/export.csv', params={'include_demo': 'true'})
        assert 'Demo1' in exp2.text

        dele = await client.delete('/demo/delete')
        assert dele.status_code == 200
        counts2 = await client.get('/demo/counts')
        assert counts2.json()['work_items']['demo'] == 0
