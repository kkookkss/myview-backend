from random         import randrange
from django.http    import JsonResponse
from django.views   import View
from django.db      import transaction
from rest_framework.views import APIView

from core.utils     import login_decorator
from core.storages  import FileHander, s3_client
from movies.models  import Image, MovieGenre, ThumbnailImage
from reviews.models import ColorCode, Place, ReviewImage, ReviewPlace, Tag, Review, ReviewTag
from users.models   import User
from my_settings    import AWS_S3_URL

class ReviewView(APIView):
    @login_decorator
    def get(self, request, review_id):
        try:
            user   = request.user
            review = Review.objects.get(id=review_id)
            result = { 
                'review_id'     : review.id,
                'title'         : review.title,
                'content'       : review.content,
                'rating'        : review.rating,
                'with_user'     : review.with_user,
                'watched_date'  : f'{review.watched_date} {review.watched_time}',
                'review_images' : [AWS_S3_URL+review_image.image.image_url for review_image in ReviewImage.objects.filter(review=review)],
                #값이 없을 경우 리턴 값 설정
                'place'         : {
                        'name' : ReviewPlace.objects.get(review_id=review_id).place.name,
                        'mapx' : ReviewPlace.objects.get(review_id=review_id).place.mapx,
                        'mapy' : ReviewPlace.objects.get(review_id=review_id).place.mapy,
                        'link' : ReviewPlace.objects.get(review_id=review_id).place.link   
                } if ReviewPlace.objects.filter(review_id=review_id).exists() else [],
                'tags'          : [
                    {
                        'tag'   : review_tag.tag.name, 
                        'color' : ColorCode.objects.get(id=randrange(0,4))
                    } for review_tag in ReviewTag.objects.filter(review=review)],
                'movie'         : {
                    'id'       : review.movie.id,
                    'title'    : review.movie.title,
                    'country'  : review.movie.country.name,
                    'category' : review.movie.category.name,
                }
            }
        
            return JsonResponse({'message' : 'SUCCESS', 'result' : result}, status=200)

        except KeyError:
            return JsonResponse({'message' : 'KEY_ERROR'}, status=400)
        
        except ValueError:
            return JsonResponse({'message' : 'VALUE_ERROR'}, status=400)
        
    @login_decorator
    @transaction.atomic(using='default')
    def post(self, request):
        try:
            data   = request.data['data']
            if Review.objects.filter(user=request.user, movie_id=data['movie_id']).exists():
                return JsonResponse({'message' : 'REVIEW_ALREADY_EXSISTS'}, status=403)
            
            review = Review.objects.create(
                user         = request.user,
                movie_id     = data['movie_id'],
                title        = data['title'],
                content      = data['content'],
                rating       = data['rating'],
                watched_date = data['watched_date'].split(' ')[0],
                watched_time = data['watched_date'].split(' ')[1],
                with_user    = data['with_user']
            )
            
            place = data.get('place', None)
            
            if place != None:
                place = Place.objects.create(
                    mapx = place['mapx', 0],
                    mapy = place['mapy', 0],
                    name = place['name'],
                    link = place['link']
                )
            
            file_handler = FileHander(s3_client)
            
            review_images = data.getlist('review_images', None)
            
            if review_images != None :
                for review_image in review_images:
                    file_name = file_handler.upload(review_image,'image/review')
                    image     = Image.objects.create(image_url=file_name)
                    
                    ReviewImage.objects.create(
                        image  = image,
                        review = review,
                    )
                
            tags = data.getlist('tags', None)
            
            if tags not in [None, '']:
                for tag_name in tags.split(','):
                    tag = Tag.objects.get_or_create(name=tag_name.strip())
                    ReviewTag.objects.create(
                        review = review,
                        tag    = tag[0]
                    )
            
            return JsonResponse({'message' : 'SUCCESS'}, status=201)
                
        except KeyError:
            return JsonResponse({'message' : 'KEY_ERROR'}, status=400)

    @login_decorator
    @transaction.atomic(using='default')
    def patch(self, request):
        try:
            data   = request.data
            review = Review.objects.get(id=data['review_id'])
            
            for key in data.dict().keys():
                if key == 'place':
                    place = Place.objects.get_or_create(
                        mapx     = data['place']['mapx', 0],
                        mapy     = data['place']['mapy', 0],
                        defaults = {
                            'name' : data['place']['name'],
                            'link' : data['place']['link']
                        }
                    )
                    ReviewPlace.get_or_creat(
                        review = review,
                        place = place
                    )
                    
                if key == 'tags':
                    for tag_name in data['tags'].split(','):
                        tag = Tag.objects.get_or_create(name=tag_name.strip())
                        ReviewTag.objects.create(
                            review = review,
                            tag    = tag[0]
                        )
                    
                if key == 'review_images_url':
                    file_handler      = FileHander(s3_client)
                    review_images_url = data['review_images_url']
                    review_images     = [review_image.image for review_image in ReviewImage.objects.filter(review_id=review.id)]

                    for review_image in review_images:
                        if AWS_S3_URL+review_image.image_url in review_images_url:
                            continue
                        else:
                            file_handler.delete(review_image.image_url)
                            review_image.delete()

                if key == 'review_images':

                    for review_image in data['review_images']:

                        file_name = file_handler.upload(review_image,'image/review')
                        image     = Image.objects.create(image_url=file_name)

                        ReviewImage.objects.create(
                            image  = image,
                            review = review,
                        )
                if key == 'watched_date':
                    review.watched_date = data['watched_date'].split(' ')[0],
                    review.watched_time = data['watched_date'].split(' ')[1],
                
                if key == 'title':
                    review.title = data[key]
                    review.save()

                if key == 'content':                
                    review.content = data[key]
                    review.save()
                
                if key == 'with_user':                
                    review.with_user = data[key]
                    review.save()
               
                return JsonResponse({'message' : 'SUCCESS'}, status=201)
                    
        except KeyError:
            return JsonResponse({'message' : 'KEY_ERROR'}, status=400)
        
        
    @login_decorator
    def delete(self, request, review_id):
        try:
            review        = Review.objects.get(id=review_id, user=request.user)
            review_images = [review_image.image for review_image in ReviewImage.objects.filter(review=review)]
            
            file_handler = FileHander(s3_client)
            
            for review_image in review_images:
                file_handler.delete(review_image.image_url)
                review_image.delete()
            
            ReviewTag.objects.filter(review=review).delete()
            
            review.delete()

            return JsonResponse({'message' : 'NO_CONTENTS'}, status=204)
        
        except Review.DoesNotExist:
            return JsonResponse({'message' : 'REVIEW_NOT_EXIST'}, status=400)

        except KeyError:
            return JsonResponse({'message' : 'KEY_ERROR'}, status=400)

        except ValueError:
            return JsonResponse({'message' : 'VALUE_ERROR'}, status=400)

class ReviewListView(View):
    @login_decorator
    def get(self, request):
        try:
            user    = request.user
            reviews = User.objects.get(id=user.id).review_set.all().order_by('-updated_at')
            result  = [{ 
                'review_id' : review.id,
                'title'     : review.title,
                'rating'    : review.rating,
                'movie'     : {
                    'id'       : review.movie.id,
                    'poster'   : ThumbnailImage.objects.get(movie=review.movie).image.image_url,
                    'title'    : review.movie.title,
                    'en_title' : review.movie.en_title,
                    'released' : review.movie.release_date,
                    'country'  : review.movie.country.name,
                    'genre'    : [movie.genre.name for movie in MovieGenre.objects.filter(movie=review.movie)],
                    'age'      : review.movie.age,
                }
            } for review in reviews]
            
            return JsonResponse({'message' : 'SUCCESS', 'result' : result}, status=200)
        
        except KeyError:
            return JsonResponse({'message' : 'KEY_ERROR'}, status=400)
            
        except ValueError:
            return JsonResponse({'message' : 'VALUE_ERROR'}, status=400)
